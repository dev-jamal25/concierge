"""Unit tests for PIIRedactionMiddleware (T035)."""

from __future__ import annotations

import io
import json
import logging
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.frameworks.api.middleware.pii_redaction import (
    PIIRedactionMiddleware,
    RedactionService,
    regex_redactor,
)
from app.frameworks.observability.logging import (
    CONCIERGE_LOGGER,
    JsonFormatter,
    get_redaction_filter,
)
from app.frameworks.observability.tracing import get_redaction_processor
from app.use_cases.protocols.guardrails_client import (
    GuardrailDecision,
    GuardrailRole,
)


@pytest.fixture(autouse=True)
def _restore_redactor_slots() -> None:
    yield
    get_redaction_filter().set_redactor(lambda s: s)
    get_redaction_processor().set_redactor(lambda s: s)


def test_regex_redactor_credit_card() -> None:
    assert regex_redactor("pay with 4242 4242 4242 4242 now") == "pay with [REDACTED] now"


def test_regex_redactor_email() -> None:
    assert regex_redactor("ping me at carla@example.com") == "ping me at [REDACTED]"


def test_regex_redactor_api_key() -> None:
    assert regex_redactor("token sk-abcdef0123456789AB ok") == "token [REDACTED] ok"


def test_regex_redactor_ssn() -> None:
    assert regex_redactor("ssn 123-45-6789 leaked") == "ssn [REDACTED] leaked"


def test_regex_redactor_passthrough_for_clean_text() -> None:
    assert regex_redactor("hello world") == "hello world"


async def _noop_app(scope, receive, send) -> None:
    return None


def test_middleware_installs_redactor_on_logging_filter() -> None:
    PIIRedactionMiddleware(_noop_app)

    logger = logging.getLogger(f"{CONCIERGE_LOGGER}.pii_test")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(get_redaction_filter())
    logger.addHandler(handler)

    logger.info("user paid with 4242 4242 4242 4242")

    payload = json.loads(stream.getvalue())
    assert payload["message"] == "user paid with [REDACTED]"


def test_middleware_redacts_structured_log_fields() -> None:
    """PII in an `extra={...}` structured field must be redacted, not just the
    rendered message (T173 structured-field redaction)."""
    PIIRedactionMiddleware(_noop_app)

    logger = logging.getLogger(f"{CONCIERGE_LOGGER}.pii_struct_test")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(get_redaction_filter())
    logger.addHandler(handler)

    logger.info("lead captured", extra={"contact_email": "carla@example.com"})

    payload = json.loads(stream.getvalue())
    assert payload["contact_email"] == "[REDACTED]"


def test_middleware_installs_redactor_on_span_processor() -> None:
    PIIRedactionMiddleware(_noop_app)

    provider = TracerProvider()
    provider.add_span_processor(get_redaction_processor())
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    tracer = provider.get_tracer("concierge.pii_test")
    with tracer.start_as_current_span("turn") as span:
        span.set_attribute("user.email", "carla@example.com")

    attrs = dict((exporter.get_finished_spans()[0].attributes or {}))
    assert attrs["user.email"] == "[REDACTED]"


class _FakeGuardrails:
    def __init__(self, decision: GuardrailDecision) -> None:
        self._decision = decision
        self.calls: list[tuple[GuardrailRole, str]] = []

    async def check(self, *, tenant_id, role: GuardrailRole, content: str) -> GuardrailDecision:
        self.calls.append((role, content))
        return self._decision


async def test_redaction_service_delegates_to_guardrails() -> None:
    decision = GuardrailDecision(
        action="redact", content="card [REDACTED]", triggered_rails=["pii_credit_card"]
    )
    fake = _FakeGuardrails(decision)
    service = RedactionService(fake)

    result = await service.redact(
        content="card 4242 4242 4242 4242", role="agent_output", tenant_id=uuid4()
    )

    assert result == "card [REDACTED]"
    assert fake.calls == [("agent_output", "card 4242 4242 4242 4242")]


def test_middleware_exposes_redaction_service_when_guardrails_provided() -> None:
    decision = GuardrailDecision(action="allow", content="hi", triggered_rails=[])
    middleware = PIIRedactionMiddleware(_noop_app, guardrails=_FakeGuardrails(decision))
    assert middleware.redaction_service is not None


def test_middleware_redaction_service_is_none_without_guardrails() -> None:
    middleware = PIIRedactionMiddleware(_noop_app)
    assert middleware.redaction_service is None
