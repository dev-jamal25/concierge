"""Service-to-service token enforcement on the modelserver (T151, FR-036).

Every call from the API to /predict carries the shared `X-Service-Token`
issued from Vault. The modelserver must reject a missing or wrong token with
401 and accept the active token with 200. `/healthz` and `/readyz` are
unauthenticated (contract: `security: []`).

These integration tests exercise the running modelserver over HTTP to avoid
importing the ONNX runtime inside the backend test environment.

Run with:
    cd backend && uv run --extra dev pytest \
        tests/integration/test_modelserver_service_token.py -v
"""

from __future__ import annotations

import hvac
import httpx
import pytest

from app.frameworks.config import get_settings

PREDICT_BODY = {"message": "what are your opening hours?", "tenant_id": None}


def _service_token_from_vault() -> str:
    settings = get_settings()
    client = hvac.Client(url=settings.vault_addr, token=settings.vault_token)
    try:
        resp = client.secrets.kv.v2.read_secret_version(
            path="service/internal-token",
            mount_point=settings.vault_kv_mount,
            raise_on_deleted_version=False,
        )
    except hvac.exceptions.InvalidPath:
        return ""
    return str(resp["data"]["data"].get("token", ""))


@pytest.fixture
def client():
    settings = get_settings()
    with httpx.Client(base_url=settings.classifier_url, timeout=10.0) as c:
        yield c


def test_predict_without_token_returns_401(client) -> None:
    resp = client.post("/predict", json=PREDICT_BODY)
    assert resp.status_code == 401


def test_predict_with_wrong_token_returns_401(client) -> None:
    resp = client.post("/predict", json=PREDICT_BODY, headers={"X-Service-Token": "wrong"})
    assert resp.status_code == 401


def test_predict_with_valid_token_returns_200(client) -> None:
    token = _service_token_from_vault()
    assert token, "service token missing in Vault; modelserver auth disabled"
    resp = client.post("/predict", json=PREDICT_BODY, headers={"X-Service-Token": token})
    assert resp.status_code == 200
    body = resp.json()
    assert body["label"] in ("spam", "faq", "lead_intent", "escalate", "ambiguous")
    assert 0.0 <= body["confidence"] <= 1.0
    assert set(body["per_class"].keys()) == {"spam", "faq", "lead_intent", "escalate", "ambiguous"}
    assert body["artifact_sha256"] == "6cfbc65825235efc576a35dec062a116078cd229dad82bddf7c402db6fabe437"


def test_healthz_requires_no_token(client) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["artifact_sha256"] == "6cfbc65825235efc576a35dec062a116078cd229dad82bddf7c402db6fabe437"
    assert body["model_card_version"] == "1.0"


def test_readyz_requires_no_token(client) -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
