"""Service-to-service token enforcement on the modelserver (T151, FR-036).

Every call from the API to /predict carries the shared `X-Service-Token`
issued from Vault. The modelserver must reject a missing or wrong token with
401 and accept the active token with 200. `/healthz` and `/readyz` are
unauthenticated (contract: `security: []`).

The modelserver module loads `services/modelserver/app.py` by file path to
avoid a name collision with the backend `app` package. TestClient's context
manager triggers the startup hook which boots the ONNX model from the
real artifacts; the service token is then overridden in-process to a known
value to exercise the auth branch without Vault.

Run with:
    cd backend && uv run --extra dev --extra notebooks pytest \\
        tests/integration/test_modelserver_service_token.py -v
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELSERVER_APP = PROJECT_ROOT / "services" / "modelserver" / "app.py"

TOKEN = "secret-modelserver-token-for-test"
PREDICT_BODY = {"message": "what are your opening hours?", "tenant_id": None}


@pytest.fixture(scope="module")
def modelserver():
    spec = importlib.util.spec_from_file_location("modelserver_app", MODELSERVER_APP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(modelserver):
    with TestClient(modelserver.app) as c:
        modelserver.SERVICE_TOKEN = TOKEN
        yield c
    modelserver.SERVICE_TOKEN = ""


def test_predict_without_token_returns_401(client) -> None:
    resp = client.post("/predict", json=PREDICT_BODY)
    assert resp.status_code == 401


def test_predict_with_wrong_token_returns_401(client) -> None:
    resp = client.post("/predict", json=PREDICT_BODY, headers={"X-Service-Token": "wrong"})
    assert resp.status_code == 401


def test_predict_with_valid_token_returns_200(client) -> None:
    resp = client.post("/predict", json=PREDICT_BODY, headers={"X-Service-Token": TOKEN})
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
