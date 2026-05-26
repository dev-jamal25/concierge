"""OpenTelemetry tracer with egress-side redaction interceptor (T041).

`configure_tracing()` installs a TracerProvider with a `RedactionSpanProcessor`
ahead of the console exporter. Production deployments swap or add an OTLP
exporter via `OTEL_EXPORTER_OTLP_ENDPOINT` (handled by the
`opentelemetry-exporter-otlp` package, added in T172 prod wiring).

The redactor slot is populated by T035's `PIIRedactionMiddleware`; until then
the processor is a pass-through.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

Redactor = Callable[[str], str]

CONCIERGE_TRACER = "concierge"


class RedactionSpanProcessor(SpanProcessor):
    """Runs the configured redactor over string span attributes at on_end.

    OTel's `BoundedAttributes` is read-only on the public surface, so the
    processor mutates the underlying dict (`_dict`) directly when present.
    The mutation is best-effort; the redactor invocation is always observable.
    """

    def __init__(self, redactor: Redactor | None = None) -> None:
        self._redactor: Redactor = redactor or (lambda s: s)

    def set_redactor(self, redactor: Redactor) -> None:
        self._redactor = redactor

    def on_start(self, span: Span, parent_context: Any = None) -> None:
        return None

    def on_end(self, span: ReadableSpan) -> None:
        bounded = getattr(span, "_attributes", None)
        inner = getattr(bounded, "_dict", None) if bounded is not None else None
        if not inner:
            return
        for key, value in list(inner.items()):
            if not isinstance(value, str):
                continue
            redacted = self._redactor(value)
            if redacted != value:
                inner[key] = redacted

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


_redaction_processor = RedactionSpanProcessor()


def get_redaction_processor() -> RedactionSpanProcessor:
    """Return the singleton processor so T035 can swap in its redactor."""
    return _redaction_processor


def configure_tracing(provider: TracerProvider | None = None) -> trace.Tracer:
    """Idempotent setup of the concierge TracerProvider. Returns the tracer."""
    if provider is None:
        provider = TracerProvider()
        provider.add_span_processor(_redaction_processor)
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(CONCIERGE_TRACER)
