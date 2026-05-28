"""GuardrailsClient protocol (T028) — Layer 2 interface.

Owner C publishes this seam; Owner B's agent and Owner C's PII middleware
code against it (never the concrete NeMo client). Mirrors the wire contract
in `specs/001-concierge-platform/contracts/internal/guardrails.yaml`
(`POST /check`).

For `action == "allow"` the returned `content` is the original input; for
`"redact"` it is the cleaned text; for `"refuse"` it is the refusal message
from the triggered rail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

GuardrailAction = Literal["allow", "redact", "refuse"]
GuardrailRole = Literal["visitor_input", "agent_output", "tool_input", "tool_output"]
GuardrailLayer = Literal["platform", "tenant"]


@dataclass(frozen=True)
class GuardrailDecision:
    action: GuardrailAction
    content: str
    triggered_rails: list[str]
    rail_layer: GuardrailLayer | None = None


class GuardrailsClient(Protocol):
    async def check(
        self,
        *,
        tenant_id: UUID,
        role: GuardrailRole,
        content: str,
    ) -> GuardrailDecision: ...
