"""Service-to-service token enforcement on the guardrails sidecar (T151, FR-036).

Every call from the API to the sidecar carries the shared `X-Service-Token`
issued from Vault. The sidecar must reject a missing or wrong token with 401 and
accept the active token with 200. `/healthz` is unauthenticated (contract:
`security: []`).

The sidecar module is literally named `app`, which collides with the backend
`app` package, so it is loaded by file path. TestClient's context manager runs
the startup hook (loading the locked platform rails); the service token is then
overridden in-process to a known value to exercise the auth branch without Vault.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SIDECAR_APP = PROJECT_ROOT / "services" / "guardrails" / "app.py"

TOKEN = "secret-service-token-for-test"
CHECK_BODY = {
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "role": "visitor_input",
    "content": "what are your hours?",
}


@pytest.fixture(scope="module")
def sidecar():
    spec = importlib.util.spec_from_file_location("guardrails_sidecar_app", SIDECAR_APP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(sidecar):
    # Context manager runs startup (loads platform rails); then pin a known token.
    with TestClient(sidecar.app) as c:
        sidecar.SERVICE_TOKEN = TOKEN
        yield c


def test_check_without_token_returns_401(client) -> None:
    resp = client.post("/check", json=CHECK_BODY)
    assert resp.status_code == 401


def test_check_with_wrong_token_returns_401(client) -> None:
    resp = client.post("/check", json=CHECK_BODY, headers={"X-Service-Token": "nope"})
    assert resp.status_code == 401


def test_check_with_valid_token_returns_200(client) -> None:
    resp = client.post("/check", json=CHECK_BODY, headers={"X-Service-Token": TOKEN})
    assert resp.status_code == 200
    assert resp.json()["action"] == "allow"


def test_healthz_requires_no_token(client) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
