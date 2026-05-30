"""Admin origins management integration tests (T116 + T117).

Tests the /admin/origins endpoint for adding, listing, and deleting allowed origins.
Requires migrations applied (alembic upgrade head).

Uses httpx.AsyncClient + ASGITransport so all async I/O shares the test's event loop,
avoiding the cross-loop contamination that occurs when mixing sync TestClient with
async pytest-asyncio tests.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.entities.user import UserRole
from app.frameworks.api.deps import db_session, manager_db_session
from app.frameworks.api.main import create_app
from app.frameworks.api.session_auth import Principal, issue_session_token
from app.frameworks.config import get_settings

os.environ.setdefault("SERVICE_TOKEN", "test-token-admin-origins")

# Share one event loop for all tests in this module to avoid cross-loop asyncpg
# socket teardown errors on Windows (IOCP proactor set to None between loops).
pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module")
async def manager_engine():
    """Module-scoped override so it matches the module loop_scope used here."""
    settings = get_settings()
    eng = create_async_engine(
        settings.manager_database_url or settings.database_url,
        poolclass=NullPool,
        future=True,
    )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(autouse=True, scope="module")
async def _require_schema(owner_engine):
    async with owner_engine.connect() as conn:
        exists = (await conn.execute(text("SELECT to_regclass('public.allowed_origins')"))).scalar()
    if exists is None:
        pytest.skip("schema not migrated; run `alembic upgrade head` first")


@pytest_asyncio.fixture(scope="module")
async def client(manager_engine) -> AsyncIterator[AsyncClient]:
    app = create_app()
    sessionmaker = async_sessionmaker(manager_engine, expire_on_commit=False)

    async def override_manager_db_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            async with session.begin():
                yield session

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            async with session.begin():
                yield session

    app.dependency_overrides[manager_db_session] = override_manager_db_session
    app.dependency_overrides[db_session] = override_db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _admin_token(tenant_id: str) -> str:
    return issue_session_token(
        Principal(user_id=str(uuid4()), role=UserRole.TENANT_ADMIN, tenant_id=tenant_id)
    )


async def test_add_origin_success(client: AsyncClient, owner_engine) -> None:
    """Test adding an allowed origin."""
    tenant_id = uuid4()

    async with owner_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {
                "id": str(tenant_id),
                "slug": f"origin-test-{tenant_id.hex[:8]}",
                "name": "Origin Test",
            },
        )
        await conn.execute(
            text(
                "INSERT INTO widgets (id, tenant_id, public_id, is_enabled) "
                "VALUES (:id, :tenant_id, :public_id, true)"
            ),
            {
                "id": str(uuid4()),
                "tenant_id": str(tenant_id),
                "public_id": f"wgt_{tenant_id.hex[:12]}",
            },
        )

    resp = await client.post(
        "/admin/origins",
        headers={"Authorization": f"Bearer {_admin_token(str(tenant_id))}"},
        json={"origin": "https://example.com"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["origin"] == "https://example.com"
    assert data["tenant_id"] == str(tenant_id)
    assert "id" in data


async def test_add_origin_duplicate_rejected(client: AsyncClient, owner_engine) -> None:
    """Test that duplicate origins are rejected."""
    tenant_id = uuid4()
    origin = "https://example.com"

    async with owner_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {
                "id": str(tenant_id),
                "slug": f"dup-origin-{tenant_id.hex[:8]}",
                "name": "Duplicate Origin Test",
            },
        )
        await conn.execute(
            text(
                "INSERT INTO widgets (id, tenant_id, public_id, is_enabled) "
                "VALUES (:id, :tenant_id, :public_id, true)"
            ),
            {
                "id": str(uuid4()),
                "tenant_id": str(tenant_id),
                "public_id": f"wgt_{tenant_id.hex[:12]}",
            },
        )
        await conn.execute(
            text(
                "INSERT INTO allowed_origins (tenant_id, origin) "
                "VALUES (:tenant_id, :origin)"
            ),
            {"tenant_id": str(tenant_id), "origin": origin},
        )

    # Try to add the same origin again
    resp = await client.post(
        "/admin/origins",
        headers={"Authorization": f"Bearer {_admin_token(str(tenant_id))}"},
        json={"origin": origin},
    )
    assert resp.status_code == 409, resp.text
    assert "already allowed" in resp.json()["detail"]


async def test_add_origin_invalid_format(client: AsyncClient, owner_engine) -> None:
    """Test that invalid origin formats are rejected."""
    tenant_id = uuid4()

    async with owner_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {
                "id": str(tenant_id),
                "slug": f"invalid-origin-{tenant_id.hex[:8]}",
                "name": "Invalid Origin Test",
            },
        )
        await conn.execute(
            text(
                "INSERT INTO widgets (id, tenant_id, public_id, is_enabled) "
                "VALUES (:id, :tenant_id, :public_id, true)"
            ),
            {
                "id": str(uuid4()),
                "tenant_id": str(tenant_id),
                "public_id": f"wgt_{tenant_id.hex[:12]}",
            },
        )

    invalid_origins = [
        "not-a-valid-origin",
        "ftp://example.com",
        "example.com",
        "http://",
    ]

    for invalid_origin in invalid_origins:
        resp = await client.post(
            "/admin/origins",
            headers={"Authorization": f"Bearer {_admin_token(str(tenant_id))}"},
            json={"origin": invalid_origin},
        )
        assert resp.status_code == 400, f"Expected 400 for {invalid_origin}, got {resp.status_code}: {resp.text}"


async def test_list_origins(client: AsyncClient, owner_engine) -> None:
    """Test listing allowed origins for a tenant."""
    tenant_id = uuid4()
    origins = ["https://example1.com", "https://example2.com", "http://localhost:3000"]

    async with owner_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {
                "id": str(tenant_id),
                "slug": f"list-origins-{tenant_id.hex[:8]}",
                "name": "List Origins Test",
            },
        )
        await conn.execute(
            text(
                "INSERT INTO widgets (id, tenant_id, public_id, is_enabled) "
                "VALUES (:id, :tenant_id, :public_id, true)"
            ),
            {
                "id": str(uuid4()),
                "tenant_id": str(tenant_id),
                "public_id": f"wgt_{tenant_id.hex[:12]}",
            },
        )
        for origin in origins:
            await conn.execute(
                text(
                    "INSERT INTO allowed_origins (tenant_id, origin) "
                    "VALUES (:tenant_id, :origin)"
                ),
                {"tenant_id": str(tenant_id), "origin": origin},
            )

    resp = await client.get(
        "/admin/origins",
        headers={"Authorization": f"Bearer {_admin_token(str(tenant_id))}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 3
    returned_origins = {item["origin"] for item in data}
    assert returned_origins == set(origins)


async def test_delete_origin_success(client: AsyncClient, owner_engine) -> None:
    """Test deleting an allowed origin."""
    tenant_id = uuid4()
    origin_id = uuid4()

    async with owner_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {
                "id": str(tenant_id),
                "slug": f"delete-origin-{tenant_id.hex[:8]}",
                "name": "Delete Origin Test",
            },
        )
        await conn.execute(
            text(
                "INSERT INTO widgets (id, tenant_id, public_id, is_enabled) "
                "VALUES (:id, :tenant_id, :public_id, true)"
            ),
            {
                "id": str(uuid4()),
                "tenant_id": str(tenant_id),
                "public_id": f"wgt_{tenant_id.hex[:12]}",
            },
        )
        await conn.execute(
            text(
                "INSERT INTO allowed_origins (id, tenant_id, origin) "
                "VALUES (:id, :tenant_id, :origin)"
            ),
            {"id": str(origin_id), "tenant_id": str(tenant_id), "origin": "https://example.com"},
        )

    resp = await client.delete(
        f"/admin/origins/{origin_id}",
        headers={"Authorization": f"Bearer {_admin_token(str(tenant_id))}"},
    )
    assert resp.status_code == 204, resp.text

    # Verify it was deleted
    list_resp = await client.get(
        "/admin/origins",
        headers={"Authorization": f"Bearer {_admin_token(str(tenant_id))}"},
    )
    assert list_resp.status_code == 200, list_resp.text
    assert len(list_resp.json()) == 0


async def test_delete_origin_cross_tenant_denied(client: AsyncClient, owner_engine) -> None:
    """Test that a tenant admin cannot delete origins from another tenant."""
    tenant_a = uuid4()
    tenant_b = uuid4()
    origin_id = uuid4()

    async with owner_engine.begin() as conn:
        for tenant_id in [tenant_a, tenant_b]:
            await conn.execute(
                text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :name)"),
                {
                    "id": str(tenant_id),
                    "slug": f"cross-tenant-{tenant_id.hex[:8]}",
                    "name": f"Cross Tenant Test {tenant_id.hex[:4]}",
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO widgets (id, tenant_id, public_id, is_enabled) "
                    "VALUES (:id, :tenant_id, :public_id, true)"
                ),
                {
                    "id": str(uuid4()),
                    "tenant_id": str(tenant_id),
                    "public_id": f"wgt_{tenant_id.hex[:12]}",
                },
            )
        # Insert origin for tenant_a
        await conn.execute(
            text(
                "INSERT INTO allowed_origins (id, tenant_id, origin) "
                "VALUES (:id, :tenant_id, :origin)"
            ),
            {"id": str(origin_id), "tenant_id": str(tenant_a), "origin": "https://example.com"},
        )

    # Try to delete tenant_a's origin as tenant_b admin.
    # RLS hides tenant_a's row from tenant_b's session before the app-level ownership
    # check runs, so the route returns 404 ("not found") rather than 403 ("forbidden").
    # 404 is the correct secure behavior: it does not reveal that the origin ID exists.
    resp = await client.delete(
        f"/admin/origins/{origin_id}",
        headers={"Authorization": f"Bearer {_admin_token(str(tenant_b))}"},
    )
    assert resp.status_code == 404, resp.text


async def test_get_widget_info(client: AsyncClient, owner_engine) -> None:
    """Test getting widget info for the current tenant."""
    tenant_id = uuid4()
    widget_public_id = f"wgt_{tenant_id.hex[:12]}"

    async with owner_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {
                "id": str(tenant_id),
                "slug": f"widget-info-{tenant_id.hex[:8]}",
                "name": "Widget Info Test",
            },
        )
        await conn.execute(
            text(
                "INSERT INTO widgets (id, tenant_id, public_id, is_enabled) "
                "VALUES (:id, :tenant_id, :public_id, true)"
            ),
            {
                "id": str(uuid4()),
                "tenant_id": str(tenant_id),
                "public_id": widget_public_id,
            },
        )

    resp = await client.get(
        "/admin/widget",
        headers={"Authorization": f"Bearer {_admin_token(str(tenant_id))}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["widget_id"] == widget_public_id
    assert data["is_enabled"] is True


async def test_get_widget_info_not_found(client: AsyncClient, owner_engine) -> None:
    """Test getting widget info when no widget exists for the tenant."""
    tenant_id = uuid4()

    async with owner_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {
                "id": str(tenant_id),
                "slug": f"no-widget-{tenant_id.hex[:8]}",
                "name": "No Widget Test",
            },
        )

    resp = await client.get(
        "/admin/widget",
        headers={"Authorization": f"Bearer {_admin_token(str(tenant_id))}"},
    )
    assert resp.status_code == 404, resp.text
