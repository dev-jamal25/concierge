"""Erasure-path integration tests (T128, T129) — SC-009 gate.

Verifies that DELETE /manager/tenants/{id}:
  1. Returns 202 ACCEPTED.
  2. Cascade-deletes all Owner A Postgres rows scoped to that tenant.
  3. Writes a ``tenant_erase_complete`` audit entry (T128) including the
     four-store ``stores_purged`` manifest and a non-negative ``duration_ms``.
  4. Leaves the erased tenant's rows invisible to a concierge_app session.
  5. Calls SessionStore.delete_by_tenant for the erased tenant (T129).
  6. Does not call SessionStore.delete_by_tenant for other tenants (T129).
  7. Writes a ``tenant_erase_start`` audit entry before erasure (T129 auditor fix).
  8. Purges MinIO objects under the tenant prefix via
     ObjectStorage.delete_prefix(tenant_id, "") (T129 MinIO half).
  9. Does not purge any other tenant's MinIO prefix (T129 MinIO isolation).

Requires: migrations applied (alembic upgrade head), compose stack running.
Skips automatically when Postgres is unreachable or the schema is absent.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.entities.user import UserRole
from app.frameworks.api.deps import (
    get_object_storage,
    get_session_store,
    manager_db_session,
)
from app.frameworks.api.main import create_app
from app.frameworks.api.session_auth import Principal, issue_session_token

pytestmark = pytest.mark.asyncio

MANAGER_ID = uuid4()


# ---------------------------------------------------------------------------
# Fakes (in-process, no real Redis / MinIO)
# ---------------------------------------------------------------------------


class FakeSessionStore:
    """Minimal in-memory SessionStore for T129 injection tests.

    Records which tenant_id values were passed to delete_by_tenant so tests can
    assert the use case invoked the correct purge without touching real Redis.
    """

    def __init__(self) -> None:
        self.purged: list[UUID] = []

    async def store(self, key: str, value: Any, ttl: int) -> None: ...  # noqa: D102

    async def retrieve(self, key: str) -> Any | None:  # noqa: D102
        return None

    async def delete(self, key: str) -> None: ...  # noqa: D102

    async def delete_by_tenant(self, tenant_id: UUID) -> None:  # noqa: D102
        self.purged.append(tenant_id)


class FakeObjectStorage:
    """Minimal in-memory ObjectStorage for T129 MinIO-half injection tests.

    Records (tenant_id, prefix) tuples passed to ``delete_prefix`` so tests can
    assert the use case purges exactly the erased tenant's MinIO objects, with
    the empty-prefix call shape required by the MinIOObjectStorage adapter
    (which already prepends ``tenant-{tenant_id}/``).
    """

    def __init__(self) -> None:
        self.purged: list[tuple[UUID, str]] = []

    async def store_object(self, tenant_id: UUID, path: str, data: bytes) -> None:  # noqa: D102
        return None

    async def fetch_object(self, tenant_id: UUID, path: str) -> bytes:  # noqa: D102
        return b""

    async def delete_object(self, tenant_id: UUID, path: str) -> None:  # noqa: D102
        return None

    async def delete_prefix(self, tenant_id: UUID, prefix: str) -> None:  # noqa: D102
        self.purged.append((tenant_id, prefix))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _require_schema(owner_engine) -> None:
    async with owner_engine.connect() as conn:
        exists = (
            await conn.execute(text("SELECT to_regclass('public.widgets')"))
        ).scalar()
    if exists is None:
        pytest.skip("schema not migrated; run `alembic upgrade head` first")


@pytest_asyncio.fixture(autouse=True)
async def _seed_manager(owner_engine) -> None:
    async with owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role) "
                "VALUES (:id, :email, 'x', 'tenant_manager') ON CONFLICT (id) DO NOTHING"
            ),
            {"id": str(MANAGER_ID), "email": f"mgr-{MANAGER_ID}@x.test"},
        )


@pytest.fixture
def client(manager_engine) -> Iterator[TestClient]:
    app = create_app()
    sessionmaker = async_sessionmaker(manager_engine, expire_on_commit=False)

    async def override_manager_db_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            async with session.begin():
                yield session

    app.dependency_overrides[manager_db_session] = override_manager_db_session
    # Always override get_object_storage in this fixture too, otherwise FastAPI
    # would try to construct a real Minio client at request time and fail in
    # environments without a live MinIO. Tests that use this fixture do not
    # inspect object-storage calls; they just need the dependency to resolve.
    app.dependency_overrides[get_object_storage] = lambda: FakeObjectStorage()
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_fake_session(
    manager_engine,
) -> Iterator[tuple[TestClient, FakeSessionStore, FakeObjectStorage]]:
    """Like `client`, but overrides both get_session_store and get_object_storage
    with in-memory fakes.

    Yields (TestClient, fake_store, fake_object_storage) so tests can inspect
    purged tenant IDs / MinIO prefixes without touching real Redis or MinIO.
    """
    app = create_app()
    sessionmaker = async_sessionmaker(manager_engine, expire_on_commit=False)
    fake_store = FakeSessionStore()
    fake_object_storage = FakeObjectStorage()

    async def override_manager_db_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            async with session.begin():
                yield session

    app.dependency_overrides[manager_db_session] = override_manager_db_session
    app.dependency_overrides[get_session_store] = lambda: fake_store
    app.dependency_overrides[get_object_storage] = lambda: fake_object_storage
    with TestClient(app) as tc:
        yield tc, fake_store, fake_object_storage
    app.dependency_overrides.clear()


def _manager_token() -> str:
    return issue_session_token(
        Principal(user_id=str(MANAGER_ID), role=UserRole.TENANT_MANAGER)
    )


async def _provision(client: TestClient) -> UUID:
    """Provision a fresh tenant and return its UUID."""
    slug = f"erase-{uuid4().hex[:8]}"
    resp = client.post(
        "/manager/tenants",
        headers={"Authorization": f"Bearer {_manager_token()}"},
        json={
            "display_name": "Erasure Test Tenant",
            "slug": slug,
            "first_admin_email": f"admin@{slug}.example.com",
            "seed_allowed_origins": [f"https://{slug}.example.com"],
        },
    )
    assert resp.status_code == 201, resp.text
    return UUID(resp.json()["id"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_erase_returns_202(client: TestClient, owner_engine) -> None:
    """DELETE /manager/tenants/{id} must return 202 ACCEPTED (T128, SC-009)."""
    tenant_id = await _provision(client)
    resp = client.delete(
        f"/manager/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {_manager_token()}"},
    )
    assert resp.status_code == 202, resp.text


async def test_erase_cascades_owner_a_tables(
    client: TestClient, owner_engine
) -> None:
    """After erasure, all Owner A rows scoped to that tenant must be gone.

    Tables verified (owner connection bypasses RLS to see true counts):
      widgets, allowed_origins, user_tenant_roles, invitations.

    The tenants row itself is deleted; the cascade removes all the rest.
    """
    tenant_id = await _provision(client)

    # Confirm rows exist before erasure.
    async with owner_engine.connect() as conn:
        for table in ("widgets", "allowed_origins", "invitations"):
            count = (
                await conn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"),
                    {"t": str(tenant_id)},
                )
            ).scalar_one()
            assert count >= 1, f"{table} should have at least 1 row before erasure"

    client.delete(
        f"/manager/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {_manager_token()}"},
    )

    # After erasure: zero rows in every Owner A table for this tenant.
    async with owner_engine.connect() as conn:
        # tenant row itself
        tenant_row = (
            await conn.execute(
                text("SELECT count(*) FROM tenants WHERE id = :t"),
                {"t": str(tenant_id)},
            )
        ).scalar_one()
        assert tenant_row == 0, "tenants row must be deleted"

        for table in ("widgets", "allowed_origins", "user_tenant_roles", "invitations"):
            count = (
                await conn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"),
                    {"t": str(tenant_id)},
                )
            ).scalar_one()
            assert count == 0, f"{table} must have 0 rows after erasure (got {count})"


async def test_erase_audit_entry_written(
    client: TestClient, owner_engine
) -> None:
    """Erasure must write a ``tenant_erase_complete`` audit entry (T128, T129).

    Asserts both that exactly one entry exists and that its ``details`` payload
    carries the full four-store ``stores_purged`` manifest (including
    ``"minio"``) plus a non-negative integer ``duration_ms`` (T129 MinIO half).
    """
    import json

    tenant_id = await _provision(client)
    client.delete(
        f"/manager/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {_manager_token()}"},
    )

    async with owner_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT details FROM audit_entries "
                    "WHERE target_tenant_id = :t AND action = 'tenant_erase_complete' "
                    "AND outcome = 'success'"
                ),
                {"t": str(tenant_id)},
            )
        ).fetchall()
    assert len(rows) == 1, (
        "tenant_erase_complete audit entry must be written exactly once"
    )
    raw_details = rows[0][0]
    details = json.loads(raw_details) if isinstance(raw_details, str) else raw_details
    stores_purged = details.get("stores_purged", [])
    assert "minio" in stores_purged, (
        f"stores_purged must include 'minio' (T129 MinIO half); got {stores_purged!r}"
    )
    duration_ms = details.get("duration_ms")
    assert isinstance(duration_ms, int) and duration_ms >= 0, (
        f"duration_ms must be a non-negative int (T129); got {duration_ms!r}"
    )


async def test_erased_tenant_rows_invisible_to_app_role(
    client: TestClient, owner_engine, app_engine
) -> None:
    """After erasure, concierge_app scoped to the erased tenant sees zero rows.

    The tenant row is deleted, so RLS (id = current_setting('app.tenant_id'))
    finds nothing — erased tenant reads are blocked structurally.
    """
    tenant_id = await _provision(client)
    client.delete(
        f"/manager/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {_manager_token()}"},
    )

    async with app_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            rows = (
                await conn.execute(text("SELECT id FROM tenants"))
            ).fetchall()
    assert len(rows) == 0, (
        "concierge_app scoped to an erased tenant must see zero tenant rows"
    )


async def test_erase_purges_redis_sessions(
    client_with_fake_session: tuple[TestClient, FakeSessionStore, FakeObjectStorage],
) -> None:
    """EraseTenantUseCase must call SessionStore.delete_by_tenant (T129).

    Uses an in-memory FakeSessionStore — no real Redis is required. Verifies that
    the erased tenant_id appears in fake_store.purged after DELETE completes.
    """
    tc, fake_store, _ = client_with_fake_session
    tenant_id = await _provision(tc)
    tc.delete(
        f"/manager/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {_manager_token()}"},
    )
    assert tenant_id in fake_store.purged, (
        "SessionStore.delete_by_tenant must be called with the erased tenant_id (T129)"
    )


async def test_erase_does_not_purge_other_tenant_sessions(
    client_with_fake_session: tuple[TestClient, FakeSessionStore, FakeObjectStorage],
) -> None:
    """Erasing tenant A must not purge tenant B's Redis sessions (T129).

    Provisions two tenants, erases only tenant A, and asserts that tenant B's
    ID is absent from FakeSessionStore.purged.
    """
    tc, fake_store, _ = client_with_fake_session
    tenant_id_a = await _provision(tc)
    tenant_id_b = await _provision(tc)

    # Erase only tenant A.
    tc.delete(
        f"/manager/tenants/{tenant_id_a}",
        headers={"Authorization": f"Bearer {_manager_token()}"},
    )

    assert tenant_id_a in fake_store.purged, (
        "SessionStore.delete_by_tenant must be called for the erased tenant (T129)"
    )
    assert tenant_id_b not in fake_store.purged, (
        "SessionStore.delete_by_tenant must NOT be called for tenant B (T129 isolation)"
    )


async def test_erase_purges_minio_prefix(
    client_with_fake_session: tuple[TestClient, FakeSessionStore, FakeObjectStorage],
) -> None:
    """EraseTenantUseCase must call ObjectStorage.delete_prefix(tenant_id, "")
    on the MinIO seam (T129 MinIO half).

    The MinIOObjectStorage adapter prepends ``tenant-{tenant_id}/`` to the
    prefix internally, so passing an empty string is the correct call shape:
    anything else would either miss objects or double the segment.
    """
    tc, _, fake_object_storage = client_with_fake_session
    tenant_id = await _provision(tc)
    tc.delete(
        f"/manager/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {_manager_token()}"},
    )
    assert fake_object_storage.purged == [(tenant_id, "")], (
        "ObjectStorage.delete_prefix must be called exactly once with "
        f"(tenant_id, '') for the erased tenant (T129); got {fake_object_storage.purged!r}"
    )


async def test_erase_does_not_purge_other_tenant_minio(
    client_with_fake_session: tuple[TestClient, FakeSessionStore, FakeObjectStorage],
) -> None:
    """Erasing tenant A must not purge tenant B's MinIO prefix (T129 MinIO isolation).

    Provisions two tenants, erases only tenant A, and asserts the recorded
    delete_prefix calls contain (A, "") but nothing for B.
    """
    tc, _, fake_object_storage = client_with_fake_session
    tenant_id_a = await _provision(tc)
    tenant_id_b = await _provision(tc)

    tc.delete(
        f"/manager/tenants/{tenant_id_a}",
        headers={"Authorization": f"Bearer {_manager_token()}"},
    )

    assert (tenant_id_a, "") in fake_object_storage.purged, (
        "ObjectStorage.delete_prefix must be called for the erased tenant (T129)"
    )
    assert not any(t == tenant_id_b for (t, _p) in fake_object_storage.purged), (
        "ObjectStorage.delete_prefix must NOT be called for tenant B (T129 isolation)"
    )


async def test_erase_start_audit_entry_written(
    client: TestClient, owner_engine
) -> None:
    """Erasure must write a ``tenant_erase_start`` audit entry BEFORE deletion (T129).

    The erase-start entry is written as the very first action in execute() so that
    erasure intent is recorded even if a subsequent step fails. This test queries
    the audit_entries table after a successful DELETE and asserts exactly one
    erase-start entry exists for the tenant.
    """
    tenant_id = await _provision(client)
    client.delete(
        f"/manager/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {_manager_token()}"},
    )

    async with owner_engine.connect() as conn:
        count = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM audit_entries "
                    "WHERE target_tenant_id = :t AND action = 'tenant_erase_start' "
                    "AND outcome = 'success'"
                ),
                {"t": str(tenant_id)},
            )
        ).scalar_one()
    assert count == 1, "tenant_erase_start audit entry must be written before erasure"
