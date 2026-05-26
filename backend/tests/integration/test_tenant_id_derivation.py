"""tenant_id derivation tests (T149).

Tenant context comes only from the verified token (set by TenantContextMiddleware).
A body that claims a different tenant_id is rejected with 403 by the route-level
guard `require_matching_tenant` — the token always wins. No DB required.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.frameworks.api.deps import require_matching_tenant
from app.frameworks.api.middleware.tenant_context import TenantContextMiddleware

TOKEN_TENANT = "11111111-1111-1111-1111-111111111111"
SPOOF_TENANT = "99999999-9999-9999-9999-999999999999"


def _verifier(token: str) -> dict[str, str]:
    if token != "good-token":
        raise ValueError("bad token")
    return {"tenant_id": TOKEN_TENANT, "sub": "22222222-2222-2222-2222-222222222222"}


class Body(BaseModel):
    tenant_id: UUID | None = None


def _make_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(TenantContextMiddleware, token_verifier=_verifier)

    @app.post("/echo")
    def echo(body: Body, _: None = Depends(lambda: None)) -> dict[str, str]:
        require_matching_tenant(body.tenant_id)
        return {"ok": "true"}

    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    return _make_client()


def test_matching_tenant_allowed(client: TestClient) -> None:
    resp = client.post(
        "/echo",
        headers={"Authorization": "Bearer good-token"},
        json={"tenant_id": TOKEN_TENANT},
    )
    assert resp.status_code == 200


def test_body_tenant_spoof_rejected(client: TestClient) -> None:
    resp = client.post(
        "/echo",
        headers={"Authorization": "Bearer good-token"},
        json={"tenant_id": SPOOF_TENANT},
    )
    assert resp.status_code == 403


def test_no_body_tenant_allowed(client: TestClient) -> None:
    resp = client.post(
        "/echo",
        headers={"Authorization": "Bearer good-token"},
        json={},
    )
    assert resp.status_code == 200


def test_body_tenant_without_token_rejected(client: TestClient) -> None:
    # No verified token → no context → a body claiming a tenant cannot be honored.
    resp = client.post("/echo", json={"tenant_id": TOKEN_TENANT})
    assert resp.status_code == 403
