"""PIIRedactionMiddleware (T035) — Layer 4.

Wires the platform's redaction seams at app startup:
* the structured-JSON logger's `RedactionFilter` (T040)
* the OpenTelemetry `RedactionSpanProcessor` (T041)
* an async `RedactionService` consumed by the Redis session writer and any
  caller about to send content to the LLM

Logging and tracing run in sync contexts that cannot await, so they get a
regex-based redactor as defense-in-depth. The async path delegates to the
guardrails sidecar (T028 protocol, T172 wiring) for full coverage.
"""

from __future__ import annotations

import re
from typing import Final
from uuid import UUID

from starlette.types import ASGIApp, Receive, Scope, Send

from app.frameworks.observability.logging import get_redaction_filter
from app.frameworks.observability.tracing import get_redaction_processor
from app.use_cases.protocols.guardrails_client import GuardrailRole, GuardrailsClient

_REDACTED: Final = "[REDACTED]"

# Conservative, non-exhaustive patterns; the full set lives in the guardrails
# sidecar (T172). These exist so logs and traces never carry obvious PII even
# before the sidecar is reachable.
_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"), _REDACTED),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), _REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), _REDACTED),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), _REDACTED),
)


def regex_redactor(s: str) -> str:
    """Sync regex redactor; safe for the logging filter and span processor."""
    for pattern, replacement in _PATTERNS:
        s = pattern.sub(replacement, s)
    return s


class RedactionService:
    """Async redactor backed by the guardrails sidecar."""

    def __init__(self, guardrails: GuardrailsClient) -> None:
        self._guardrails = guardrails

    async def redact(self, *, content: str, role: GuardrailRole, tenant_id: UUID) -> str:
        decision = await self._guardrails.check(
            tenant_id=tenant_id, role=role, content=content
        )
        return decision.content


class PIIRedactionMiddleware:
    """Pass-through ASGI middleware; construction installs the sync redactors.

    Owner B's session_store and LLM adapter consume `redaction_service` directly
    for guardrails-backed redaction before write / egress.
    """

    def __init__(self, app: ASGIApp, guardrails: GuardrailsClient | None = None) -> None:
        self.app = app
        self.redaction_service = RedactionService(guardrails) if guardrails else None
        get_redaction_filter().set_redactor(regex_redactor)
        get_redaction_processor().set_redactor(regex_redactor)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)
