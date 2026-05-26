"""Unit tests for tracing.py (T041)."""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.frameworks.observability.tracing import (
    RedactionSpanProcessor,
    configure_tracing,
)


def _provider_with(processor: RedactionSpanProcessor) -> tuple[TracerProvider, InMemorySpanExporter]:
    provider = TracerProvider()
    provider.add_span_processor(processor)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_redaction_processor_runs_redactor_on_string_attributes() -> None:
    seen: list[str] = []

    def redactor(s: str) -> str:
        seen.append(s)
        return s.replace("4242", "[REDACTED]")

    provider, exporter = _provider_with(RedactionSpanProcessor(redactor=redactor))
    tracer = provider.get_tracer("concierge.test")

    with tracer.start_as_current_span("chat.turn") as span:
        span.set_attribute("user.message", "my card 4242")
        span.set_attribute("tenant.id", "tnt_1")
        span.set_attribute("conversation.length", 7)  # non-string skipped

    assert "my card 4242" in seen
    assert "tnt_1" in seen
    assert all(not isinstance(s, int) for s in seen)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = dict(spans[0].attributes or {})
    assert attrs["user.message"] == "my card [REDACTED]"
    assert attrs["tenant.id"] == "tnt_1"
    assert attrs["conversation.length"] == 7


def test_redaction_processor_passthrough_by_default() -> None:
    provider, exporter = _provider_with(RedactionSpanProcessor())
    tracer = provider.get_tracer("concierge.test")
    with tracer.start_as_current_span("op") as span:
        span.set_attribute("k", "value")
    attrs = dict((exporter.get_finished_spans()[0].attributes or {}))
    assert attrs["k"] == "value"


def test_configure_tracing_returns_concierge_tracer() -> None:
    provider = TracerProvider()
    provider.add_span_processor(RedactionSpanProcessor())
    tracer = configure_tracing(provider=provider)
    assert tracer is not None
    with tracer.start_as_current_span("smoke"):
        pass
