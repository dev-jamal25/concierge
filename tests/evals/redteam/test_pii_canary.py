"""PII canary eval gate (T143).

Pastes synthetic PII canaries (a fake API key + a fake credit card) through
every surface where visitor content could leak, and asserts the raw canary
NEVER appears unredacted in any of them:

* structured logs        — JsonFormatter + RedactionFilter (T040)
* OpenTelemetry traces   — RedactionSpanProcessor (T041)
* Redis session memory   — RedactionService seam the session writer uses (T046)
* LLM input payload      — RedactionService seam the LLM adapter uses (T044)
* guardrails sidecar      — the sidecar's own evaluate() output (T172)

The Redis/LLM seam is exercised against the *real* sidecar rails (not just the
sync regex) so the gate proves the slow path redacts too. Gated at
`pii_redaction_rate == 1.0` in `eval_thresholds.yaml` (SC-008): every
(canary, surface) pair must be redacted. Runs on every CI run; a single leak
exits non-zero and blocks the merge. This threshold must never be lowered.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
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
from app.use_cases.protocols.guardrails_client import GuardrailDecision, GuardrailRole

PROJECT_ROOT = Path(__file__).resolve().parents[3]
THRESHOLDS_PATH = PROJECT_ROOT / "eval_thresholds.yaml"

# Synthetic, non-functional canaries. The credit card is the Visa test number;
# the API key is an obviously fake token. Neither is a real credential.
CANARY_CARD = "4242 4242 4242 4242"
CANARY_API_KEY = "sk-test-CANARY000000000000000000000000"
CANARIES = (CANARY_CARD, CANARY_API_KEY)


@pytest.fixture(autouse=True)
def _restore_redactor_slots():
    yield
    get_redaction_filter().set_redactor(lambda s: s)
    get_redaction_processor().set_redactor(lambda s: s)


async def _noop_app(scope, receive, send) -> None:
    return None


class _SidecarGuardrails:
    """Adapts the in-process sidecar evaluate() to the GuardrailsClient protocol,
    so the async RedactionService is exercised against the real platform rails."""

    def __init__(self, sidecar, rails) -> None:
        self._sidecar = sidecar
        self._rails = rails

    async def check(self, *, tenant_id, role: GuardrailRole, content: str) -> GuardrailDecision:
        d = self._sidecar.evaluate(content, self._rails)
        return GuardrailDecision(
            action=d.action,
            content=d.content,
            triggered_rails=d.triggered_rails,
            rail_layer=d.rail_layer,
        )


def _gate_threshold() -> float:
    thresholds = yaml.safe_load(THRESHOLDS_PATH.read_text(encoding="utf-8"))
    return float(thresholds["pii_redaction_rate"])


def _redact_in_log(message: str) -> str:
    """Emit a log record through the JSON formatter + redaction filter and return
    the serialized line."""
    PIIRedactionMiddleware(_noop_app)
    logger = logging.getLogger(f"{CONCIERGE_LOGGER}.canary_test")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(get_redaction_filter())
    logger.addHandler(handler)
    logger.info("visitor said: %s", message)
    return stream.getvalue()


def _redact_in_trace(message: str) -> str:
    """Set a span attribute to the message, export it, return the serialized
    attributes."""
    PIIRedactionMiddleware(_noop_app)
    provider = TracerProvider()
    provider.add_span_processor(get_redaction_processor())
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("concierge.canary_test")
    with tracer.start_as_current_span("turn") as span:
        span.set_attribute("visitor.message", message)
    return json.dumps(dict(exporter.get_finished_spans()[0].attributes or {}))


def test_pii_canary_never_leaks_unredacted(sidecar, platform_rails) -> None:
    """No canary may survive unredacted on any logging/tracing/persistence/egress
    surface. Asserts pii_redaction_rate == 1.0 across all (canary, surface) pairs.

    Synchronous so the gate runs regardless of pytest-asyncio config (these eval
    tests resolve their rootdir at the repo root, not backend); the async
    RedactionService seam is driven via asyncio.run."""
    threshold = _gate_threshold()
    redaction_service = RedactionService(_SidecarGuardrails(sidecar, platform_rails))
    tenant_id = uuid4()

    def redact(content: str, role: GuardrailRole) -> str:
        return asyncio.run(
            redaction_service.redact(content=content, role=role, tenant_id=tenant_id)
        )

    checks: list[tuple[str, str, str]] = []  # (surface, canary, observed_output)
    for canary in CANARIES:
        sentence = f"please charge {canary} thanks"

        checks.append(("logs", canary, _redact_in_log(sentence)))
        checks.append(("traces", canary, _redact_in_trace(sentence)))
        checks.append(("redis_session_memory", canary, redact(sentence, "visitor_input")))
        checks.append(("llm_input_payload", canary, redact(sentence, "agent_output")))
        checks.append(("guardrails_sidecar", canary, sidecar.evaluate(sentence, platform_rails).content))

    leaks = [(surface, canary) for surface, canary, output in checks if canary in output]
    redaction_rate = (len(checks) - len(leaks)) / len(checks)

    print(f"\nPII canary gate: {threshold:.2f}")
    print(f"redaction rate:  {redaction_rate:.4f}  ({len(checks) - len(leaks)}/{len(checks)} surfaces clean)")
    for surface, canary in leaks:
        print(f"  LEAK on {surface}: {canary!r} appeared unredacted")

    assert redaction_rate >= threshold, (
        f"PII canary leak: redaction_rate {redaction_rate:.4f} < gate {threshold:.2f}. "
        f"{len(leaks)} surface(s) leaked a canary unredacted. This gate is 1.0 (SC-008) "
        "and must never be lowered."
    )


def test_sync_regex_redactor_covers_canaries() -> None:
    """The sync regex fast path (logs/traces before the sidecar is reachable)
    must redact every canary on its own — defense in depth."""
    for canary in CANARIES:
        redacted = regex_redactor(f"value {canary} here")
        assert canary not in redacted, f"sync regex left {canary!r} unredacted"
        assert "[REDACTED]" in redacted


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
