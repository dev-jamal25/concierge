"""Contract tests: lead_intent route now captures leads deterministically (zero LLM).

Three properties asserted:
1. A lead_intent message with email + name writes a lead row and returns "captured".
2. AnthropicLLM.call is never invoked on the lead_intent path (guards 0-LLM cost model).
3. A message with no contact info returns not_captured and asks for contact details.
4. Rate-limited capture returns a friendly reply and the rate-limit status.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SERVICE_TOKEN", "test-token-lead-intent")

from app.frameworks.api.deps import (  # noqa: E402
    db_session,
    get_app_settings,
    get_current_widget_context,
    get_session_store,
)
from app.frameworks.api.main import create_app  # noqa: E402


class _NullSessionStore:
    async def store(self, key, value, ttl): pass
    async def retrieve(self, key): return None
    async def delete(self, key): pass
    async def delete_by_tenant(self, tenant_id): pass


class _FakeSession:
    async def execute(self, *a, **kw):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        result.scalar.return_value = 0
        return result

    async def get(self, model, pk):
        return None

    async def flush(self): pass
    async def refresh(self, obj): pass
    def add(self, obj): pass


def _fake_lead_intent_classify():
    from app.use_cases.protocols.classifier_client import ClassifierResult
    return ClassifierResult(
        label="lead_intent",
        confidence=0.91,
        per_class={"lead_intent": 0.91, "spam": 0.01, "faq": 0.04, "escalate": 0.01, "ambiguous": 0.03},
        artifact_sha256="",
    )


def _fake_lead(contact: str, name: str | None = None) -> object:
    from app.entities.lead import Lead
    from datetime import datetime, timezone
    return Lead(
        id=uuid4(),
        tenant_id=uuid4(),
        conversation_id=uuid4(),
        contact=contact,
        intent="book a table",
        name=name,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def lead_client() -> TestClient:
    from app.frameworks.api.deps import WidgetTokenContext

    app = create_app()
    tenant_id = str(uuid4())
    widget_id = str(uuid4())

    async def fake_widget_context() -> WidgetTokenContext:
        return WidgetTokenContext(
            tenant_id=tenant_id,
            widget_id=widget_id,
            origin="http://localhost:3001",
            visitor_session=None,
        )

    async def fake_db_session() -> AsyncIterator:
        yield _FakeSession()

    from app.frameworks.config import Settings

    def fake_settings() -> Settings:
        return Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            manager_database_url="postgresql+asyncpg://x:x@localhost/x",
            migration_database_url="postgresql+asyncpg://x:x@localhost/x",
            anthropic_api_key="sk-test",
            embedding_api_key="test-embed-key",
            service_token="test-token-lead-intent",
        )

    async def fake_session_store():
        return _NullSessionStore()

    app.dependency_overrides[get_current_widget_context] = fake_widget_context
    app.dependency_overrides[db_session] = fake_db_session
    app.dependency_overrides[get_app_settings] = fake_settings
    app.dependency_overrides[get_session_store] = fake_session_store

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


_MSG_WITH_CONTACT = (
    "I want to book a table for 4 tonight. "
    "My name is Jamal and my email is jamal@example.com."
)
_MSG_NO_CONTACT = "book a table for 4 tonight"


# ---------------------------------------------------------------------------
# Test 1 + 2: captures lead and never calls the LLM
# ---------------------------------------------------------------------------

def test_lead_intent_captures_when_contact_present(lead_client: TestClient) -> None:
    fake_lead = _fake_lead("jamal@example.com", "Jamal")

    llm_mock = MagicMock()

    with (
        patch(
            "app.adapters.classifier.modelserver_client.ModelserverClassifier.classify",
            new=AsyncMock(return_value=_fake_lead_intent_classify()),
        ),
        patch(
            "app.frameworks.api.routes.chat.get_guardrails_client",
            return_value=None,
        ),
        patch(
            "app.adapters.repositories.lead_repository.PostgresLeadRepository.capture",
            new=AsyncMock(return_value=fake_lead),
        ) as mock_capture,
        patch(
            "app.adapters.repositories.lead_repository.PostgresLeadRepository.count_by_session",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "app.adapters.llm.anthropic_client.AnthropicLLM.call",
            new=llm_mock,
        ),
    ):
        resp = lead_client.post(
            "/chat",
            headers={
                "Authorization": "Bearer fake-widget-token",
                "Origin": "http://localhost:3001",
            },
            json={
                "conversation_id": str(uuid4()),
                "message": _MSG_WITH_CONTACT,
            },
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["route"] == "lead_intent", f"Expected route=lead_intent, got {body['route']}"
    assert body["capture_lead_status"] == "captured", (
        f"Expected captured, got {body['capture_lead_status']}"
    )
    assert body.get("reply"), "reply should not be empty"
    # Verify the LLM was never touched (guards 0-LLM cost model)
    llm_mock.assert_not_called()
    # Verify capture was called with extracted contact + name
    mock_capture.assert_called_once()
    call_kwargs = mock_capture.call_args.kwargs
    assert call_kwargs["contact"] == "jamal@example.com", (
        f"Expected contact=jamal@example.com, got {call_kwargs['contact']}"
    )
    assert call_kwargs["name"] == "Jamal", (
        f"Expected name=Jamal, got {call_kwargs.get('name')}"
    )


# ---------------------------------------------------------------------------
# Test 3: no contact → asks for it, no capture
# ---------------------------------------------------------------------------

def test_lead_intent_no_contact_asks_for_details(lead_client: TestClient) -> None:
    llm_mock = MagicMock()

    with (
        patch(
            "app.adapters.classifier.modelserver_client.ModelserverClassifier.classify",
            new=AsyncMock(return_value=_fake_lead_intent_classify()),
        ),
        patch(
            "app.frameworks.api.routes.chat.get_guardrails_client",
            return_value=None,
        ),
        patch(
            "app.adapters.repositories.lead_repository.PostgresLeadRepository.capture",
            new=AsyncMock(),
        ) as mock_capture,
        patch(
            "app.adapters.llm.anthropic_client.AnthropicLLM.call",
            new=llm_mock,
        ),
    ):
        resp = lead_client.post(
            "/chat",
            headers={
                "Authorization": "Bearer fake-widget-token",
                "Origin": "http://localhost:3001",
            },
            json={
                "conversation_id": str(uuid4()),
                "message": _MSG_NO_CONTACT,
            },
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["route"] == "lead_intent"
    assert body["capture_lead_status"] == "not_captured"
    assert body.get("reply"), "reply should not be empty"
    mock_capture.assert_not_called()
    llm_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: rate-limited capture returns friendly reply
# ---------------------------------------------------------------------------

def test_lead_intent_rate_limited(lead_client: TestClient) -> None:
    from app.use_cases.protocols.lead_repository import RateLimitExceeded

    with (
        patch(
            "app.adapters.classifier.modelserver_client.ModelserverClassifier.classify",
            new=AsyncMock(return_value=_fake_lead_intent_classify()),
        ),
        patch(
            "app.frameworks.api.routes.chat.get_guardrails_client",
            return_value=None,
        ),
        patch(
            "app.adapters.repositories.lead_repository.PostgresLeadRepository.capture",
            new=AsyncMock(side_effect=RateLimitExceeded("rate_limit_window")),
        ),
        patch(
            "app.adapters.repositories.lead_repository.PostgresLeadRepository.count_by_session",
            new=AsyncMock(return_value=0),
        ),
    ):
        resp = lead_client.post(
            "/chat",
            headers={
                "Authorization": "Bearer fake-widget-token",
                "Origin": "http://localhost:3001",
            },
            json={
                "conversation_id": str(uuid4()),
                "message": _MSG_WITH_CONTACT,
            },
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["route"] == "lead_intent"
    assert "rate_limited" in body["capture_lead_status"], (
        f"Expected rate_limited status, got {body['capture_lead_status']}"
    )
    assert body.get("reply"), "reply should not be empty"
