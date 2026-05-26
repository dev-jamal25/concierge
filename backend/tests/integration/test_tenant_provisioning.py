"""Provisioning + invitation-acceptance integration tests (T118).

Requires migrations applied (alembic upgrade head). Skips if Postgres / schema is
unavailable. Exercises the real manager session (concierge_manager role).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.entities.user import UserRole
from app.frameworks.api.main import create_app
from app.frameworks.api.session_auth import Principal, issue_session_token
from app.use_cases.invitation_tokens import hash_token

MANAGER_ID = uuid4()


@pytest_asyncio.fixture(autouse=True)
async def _require_schema(owner_engine):
    async with owner_engine.connect() as conn:
        exists = (
            await conn.execute(
                text("SELECT to_regclass('public.widgets')")
            )
        ).scalar()
    if exists is None:
        pytest.skip("schema not migrated; run `alembic upgrade head` first")


@pytest_asyncio.fixture(autouse=True)
async def _seed_manager(owner_engine):
    async with owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role) "
                "VALUES (:id, :email, 'x', 'tenant_manager') ON CONFLICT (id) DO NOTHING"
            ),
            {"id": str(MANAGER_ID), "email": f"mgr-{MANAGER_ID}@x.test"},
        )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _manager_token() -> str:
    return issue_session_token(
        Principal(user_id=str(MANAGER_ID), role=UserRole.TENANT_MANAGER)
    )


def _admin_token(tenant_id: str) -> str:
    return issue_session_token(
        Principal(user_id=str(uuid4()), role=UserRole.TENANT_ADMIN, tenant_id=tenant_id)
    )


@pytest.mark.asyncio
async def test_provision_creates_all_rows(client: TestClient, owner_engine) -> None:
    slug = f"acme-{uuid4().hex[:8]}"
    resp = client.post(
        "/manager/tenants",
        headers={"Authorization": f"Bearer {_manager_token()}"},
        json={
            "display_name": "ACME Inc.",
            "slug": slug,
            "first_admin_email": "admin@acme.example.com",
            "seed_allowed_origins": ["https://acme.example.com"],
        },
    )
    assert resp.status_code == 201, resp.text
    tenant_id = resp.json()["id"]

    async with owner_engine.connect() as conn:
        widget = (
            await conn.execute(
                text("SELECT count(*) FROM widgets WHERE tenant_id = :t"), {"t": tenant_id}
            )
        ).scalar_one()
        origins = (
            await conn.execute(
                text("SELECT count(*) FROM allowed_origins WHERE tenant_id = :t"),
                {"t": tenant_id},
            )
        ).scalar_one()
        invites = (
            await conn.execute(
                text("SELECT count(*) FROM invitations WHERE tenant_id = :t"), {"t": tenant_id}
            )
        ).scalar_one()
        audit = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM audit_entries "
                    "WHERE target_tenant_id = :t AND action = 'tenant_create'"
                ),
                {"t": tenant_id},
            )
        ).scalar_one()

    assert widget == 1
    assert origins == 1
    assert invites == 1
    assert audit == 1


@pytest.mark.asyncio
async def test_invitation_acceptance_binds_admin(client: TestClient, owner_engine) -> None:
    # Seed a tenant + a known-token invitation directly.
    tenant_id = uuid4()
    raw_token = "test-invite-token-123"
    async with owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, 'X')"
            ),
            {"id": str(tenant_id), "slug": f"t-{tenant_id.hex[:8]}"},
        )
        await conn.execute(
            text(
                "INSERT INTO invitations (tenant_id, email, token_hash, expires_at, created_by) "
                "VALUES (:t, :email, :h, now() + interval '1 day', :by)"
            ),
            {
                "t": str(tenant_id),
                "email": "invitee@acme.example.com",
                "h": hash_token(raw_token),
                "by": str(MANAGER_ID),
            },
        )

    resp = client.post(
        f"/auth/invitations/{raw_token}/accept", json={"password": "s3cret-pass"}
    )
    assert resp.status_code == 201, resp.text

    async with owner_engine.connect() as conn:
        bound = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM user_tenant_roles utr "
                    "JOIN users u ON u.id = utr.user_id "
                    "WHERE utr.tenant_id = :t AND u.email = 'invitee@acme.example.com' "
                    "AND u.role = 'tenant_admin'"
                ),
                {"t": str(tenant_id)},
            )
        ).scalar_one()
        accepted = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM invitations "
                    "WHERE tenant_id = :t AND accepted_at IS NOT NULL"
                ),
                {"t": str(tenant_id)},
            )
        ).scalar_one()
    assert bound == 1
    assert accepted == 1


def test_tenant_admin_cannot_access_manager(client: TestClient) -> None:
    resp = client.get(
        "/manager/tenants", headers={"Authorization": f"Bearer {_admin_token(str(uuid4()))}"}
    )
    assert resp.status_code == 403
