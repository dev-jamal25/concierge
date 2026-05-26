"""Unit tests for ModelserverClassifier (T047)."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from app.adapters.classifier.modelserver_client import ModelserverClassifier


def _client_with(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, base_url="http://modelserver:8001")


@pytest.mark.asyncio
async def test_classify_parses_modelserver_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["token"] = request.headers.get("X-Service-Token")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "label": "faq",
                "confidence": 0.91,
                "per_class": {
                    "spam": 0.01,
                    "faq": 0.91,
                    "lead_intent": 0.04,
                    "escalate": 0.02,
                    "ambiguous": 0.02,
                },
                "artifact_sha256": "abc123",
            },
        )

    adapter = ModelserverClassifier(
        base_url="http://modelserver:8001",
        service_token="svc-token",
        client=_client_with(httpx.MockTransport(handler)),
    )

    tid = uuid4()
    result = await adapter.classify(message="how do I reset my password?", tenant_id=tid)

    assert captured["url"] == "http://modelserver:8001/predict"
    assert captured["method"] == "POST"
    assert captured["token"] == "svc-token"
    assert captured["body"] == {
        "message": "how do I reset my password?",
        "tenant_id": str(tid),
    }
    assert result.label == "faq"
    assert result.confidence == pytest.approx(0.91)
    assert result.per_class["faq"] == pytest.approx(0.91)
    assert result.artifact_sha256 == "abc123"


@pytest.mark.asyncio
async def test_classify_defaults_missing_artifact_sha256() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "label": "spam",
                "confidence": 0.99,
                "per_class": {"spam": 0.99},
            },
        )

    adapter = ModelserverClassifier(
        base_url="http://modelserver:8001",
        service_token="svc-token",
        client=_client_with(httpx.MockTransport(handler)),
    )

    result = await adapter.classify(message="buy now", tenant_id=uuid4())
    assert result.artifact_sha256 == ""


@pytest.mark.asyncio
async def test_classify_raises_on_401() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "missing service token"})

    adapter = ModelserverClassifier(
        base_url="http://modelserver:8001",
        service_token="",
        client=_client_with(httpx.MockTransport(handler)),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.classify(message="anything", tenant_id=uuid4())
