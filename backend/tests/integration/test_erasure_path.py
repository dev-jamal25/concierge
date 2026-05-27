"""Erasure-path integration tests (T128) — SC-009 gate.

Verifies that DELETE /manager/tenants/{id}:
  1. Returns 202 ACCEPTED.
  2. Cascade-deletes all Owner A Postgres rows scoped to that tenant.
  3. Writes a ``tenant_erase_complete`` audit entry.
  4. Leaves the erased tenant's rows invisible to a concierge_app session.

Redis / MinIO purge is deferred (T129) — those stores are not yet wired.
This test only asserts the Postgres + audit boundary, which is Owner A's scope.

Requires: migrations applied (alembic upgrade head), compose stack running.
Skips automatically when Postgres is unreachable or the schema is absent.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.entities.user import UserRole
from app.frameworks.api.deps import manager_db_session
from app.frameworks.api.main import create_app
from app.frameworks.api.session_auth import Principal, issue_session_token

pytestmark = pytest.mark.asyncio

MANAGER_ID = uuid4()


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
    with TestClient(app) as tc:
        yield tc
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
    """Erasure must write a ``tenant_erase_complete`` audit entry (T128)."""
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
                    "WHERE target_tenant_id = :t AND action = 'tenant_erase_complete' "
                    "AND outcome = 'success'"
                ),
                {"t": str(tenant_id)},
            )
        ).scalar_one()
    assert count == 1, "tenant_erase_complete audit entry must be written exactly once"


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
