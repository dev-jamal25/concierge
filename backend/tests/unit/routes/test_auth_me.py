"""Unit tests for GET /auth/me."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.entities.user import User, UserRole
from app.frameworks.api.deps import get_manager_context
from app.frameworks.api.main import create_app
from app.frameworks.api.session_auth import Principal, issue_session_token


def _make_client(user: User) -> TestClient:
    """Build a TestClient with get_manager_context overridden."""
    app = create_app()

    async def _fake_manager_context():
        ctx = MagicMock()
        ctx.users = MagicMock()
        ctx.users.get = AsyncMock(return_value=user)
        yield ctx

    app.dependency_overrides[get_manager_context] = _fake_manager_context
    return TestClient(app, raise_server_exceptions=True)


def _token(user_id: str, role: UserRole, tenant_id: str | None) -> str:
    return issue_session_token(Principal(user_id=user_id, role=role, tenant_id=tenant_id))


def test_auth_me_tenant_admin_returns_identity() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    user = User(
        id=user_id,
        email="admin@lumiere-coffee.example.com",
        hashed_password="hashed",
        role=UserRole.TENANT_ADMIN,
        is_active=True,
        is_verified=True,
        created_at=None,
    )
    client = _make_client(user)
    tok = _token(str(user_id), UserRole.TENANT_ADMIN, str(tenant_id))
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == user.email
    assert body["role"] == UserRole.TENANT_ADMIN.value
    assert body["tenant_id"] == str(tenant_id)
    assert body["user_id"] == str(user_id)


def test_auth_me_missing_token_returns_401() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_auth_me_invalid_token_returns_401() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert resp.status_code == 401


def test_auth_me_deleted_user_returns_401() -> None:
    """If the user_id in the token no longer exists in DB, return 401."""
    user_id = uuid4()
    app = create_app()

    async def _gone_user_context_gen():
        ctx = MagicMock()
        ctx.users = MagicMock()
        ctx.users.get = AsyncMock(return_value=None)
        yield ctx

    app.dependency_overrides[get_manager_context] = _gone_user_context_gen
    client = TestClient(app, raise_server_exceptions=False)
    tok = _token(str(user_id), UserRole.TENANT_ADMIN, str(uuid4()))
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 401
