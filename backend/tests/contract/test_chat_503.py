"""Contract test: /chat returns 503 (not 500) when the agent path fails.

Overrides all DB/LLM/session-store deps with fakes so no external
services are needed. Verifies the escalation error handler in chat.py
correctly absorbs a secondary failure and returns the intended 503.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SERVICE_TOKEN", "test-token-chat-503")

from app.frameworks.api.deps import (  # noqa: E402
    db_session,
    get_app_settings,
    get_current_widget_context,
    get_session_store,
)
from app.frameworks.api.main import create_app  # noqa: E402


class _FailingSessionStore:
    async def store(self, key, value, ttl): pass
    async def retrieve(self, key): return None
    async def delete(self, key): pass
    async def delete_by_tenant(self, tenant_id): pass


class _FakeSession:
    """Minimal AsyncSession stand-in. execute() always succeeds; get() returns None."""

    async def execute(self, *a, **kw):
        from unittest.mock import MagicMock
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        return result

    async def get(self, model, pk):
        return None

    async def flush(self): pass
    async def refresh(self, obj): pass

    def add(self, obj): pass


@pytest.fixture
def client_503() -> TestClient:
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
            anthropic_api_key="",
            embedding_api_key="",
            service_token="test-token-chat-503",
        )

    async def fake_session_store():
        return _FailingSessionStore()

    app.dependency_overrides[get_current_widget_context] = fake_widget_context
    app.dependency_overrides[db_session] = fake_db_session
    app.dependency_overrides[get_app_settings] = fake_settings
    app.dependency_overrides[get_session_store] = fake_session_store

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def test_chat_agent_failure_returns_503_not_500(client_503: TestClient) -> None:
    """When the agent path fails (no LLM key) and escalation also fails
    (conversation not found in session), /chat must return 503, not 500.

    Three patches to reach the target code path:
    1. Classifier → "ambiguous" so we route to agent_turn
    2. get_guardrails_client → None so agent bypasses guardrails and reaches the LLM call
    3. AnthropicLLM.call → raises so agent's except block fires, calling escalate
    Escalate then raises LookupError (fake session returns None), which propagates
    to chat.py's except block and results in the intended 503.
    """
    from app.use_cases.protocols.classifier_client import ClassifierResult

    fake_classify_result = ClassifierResult(
        label="ambiguous",
        confidence=1.0,
        per_class={},
        artifact_sha256="",
    )
    with (
        patch(
            "app.adapters.classifier.modelserver_client.ModelserverClassifier.classify",
            new=AsyncMock(return_value=fake_classify_result),
        ),
        patch(
            "app.frameworks.api.routes.chat.get_guardrails_client",
            return_value=None,
        ),
        patch(
            "app.adapters.llm.anthropic_client.AnthropicLLM.call",
            new=AsyncMock(side_effect=RuntimeError("LLM unavailable")),
        ),
    ):
        resp = client_503.post(
            "/chat",
            headers={
                "Authorization": "Bearer fake-widget-token",
                "Origin": "http://localhost:3001",
            },
            json={
                "conversation_id": str(uuid4()),
                "message": "What are Helix Analytics private API secrets?",
            },
        )
    assert resp.status_code == 503, f"Expected 503, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("detail", {}).get("escalated") is True


def test_chat_rag_search_embedding_failure_returns_200_not_503(client_503: TestClient) -> None:
    """When the embedding API fails during a rag_search tool call, /chat must return
    200 with a graceful reply, not 503.

    Before the fix, a transient Voyage/embedding 400/429/timeout in agent_turn's
    rag_search execution propagated uncaught and triggered the 503 handler in chat.py.

    Four patches:
    1. Classifier → "ambiguous" so we route to agent_turn
    2. get_guardrails_client → None so agent bypasses guardrails
    3. AnthropicLLM.call → [rag_search tool call, then end_turn reply]
    4. HostedEmbeddings.embed → always raises (simulates embedding outage)

    agent_turn now catches the rag_search failure and returns empty chunks so the
    LLM can still produce a reply.  chat.py receives a normal AgentTurnResult (no
    exception) and returns 200 with route="agent".
    """
    from app.use_cases.protocols.classifier_client import ClassifierResult
    from app.use_cases.protocols.llm_client import LLMResponse

    fake_classify_result = ClassifierResult(
        label="ambiguous",
        confidence=1.0,
        per_class={},
        artifact_sha256="",
    )
    rag_tool_response = LLMResponse(
        content="",
        tool_calls=[{"id": "tc-embed-fail", "name": "rag_search", "input": {"query": "what are your hours"}}],
        stop_reason="tool_use",
    )
    final_response = LLMResponse(
        content="I don't have specific information about that right now.",
        tool_calls=[],
        stop_reason="end_turn",
    )

    with (
        patch(
            "app.adapters.classifier.modelserver_client.ModelserverClassifier.classify",
            new=AsyncMock(return_value=fake_classify_result),
        ),
        patch(
            "app.frameworks.api.routes.chat.get_guardrails_client",
            return_value=None,
        ),
        patch(
            "app.adapters.llm.anthropic_client.AnthropicLLM.call",
            new=AsyncMock(side_effect=[rag_tool_response, final_response]),
        ),
        patch(
            "app.adapters.embeddings.hosted_embeddings.HostedEmbeddings.embed",
            new=AsyncMock(side_effect=RuntimeError("embedding service unavailable")),
        ),
    ):
        resp = client_503.post(
            "/chat",
            headers={
                "Authorization": "Bearer fake-widget-token",
                "Origin": "http://localhost:3001",
            },
            json={
                "conversation_id": str(uuid4()),
                "message": "what are your hours?",
            },
        )
    assert resp.status_code == 200, f"Expected 200 (graceful degradation), got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("route") == "agent"
    assert body.get("escalated") is False
    assert body.get("reply")  # LLM still provides a reply despite empty search context
