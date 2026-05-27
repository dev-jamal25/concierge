"""GuardrailConfig entity (T122) — Layer 1.

Pure stdlib dataclass. Carries the per-tenant configurable rail surface that the
guardrails sidecar (T172) and the admin update use case (T123) both reference.

`enabled_tools` is bounded to the agent's known tool set; values outside that set
are a programming error and `validate()` raises `ValueError`. Whether a config
weakens platform rails (a *policy* concern, not a *shape* concern) is enforced
in the use case, not here -- entities know data, not authorization.

Constitution Principle I: no imports from adapters, frameworks, or third-party
libraries beyond the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar
from uuid import UUID


@dataclass(slots=True)
class GuardrailConfig:
    """Per-tenant configurable guardrails -- shape only, no policy enforcement."""

    ALLOWED_TOOLS: ClassVar[frozenset[str]] = frozenset(
        {"rag_search", "capture_lead", "escalate"}
    )

    tenant_id: UUID
    updated_at: datetime
    allowed_topics: list[str] = field(default_factory=list)
    blocked_topics: list[str] = field(default_factory=list)
    refusal_tone: str = "polite"
    enabled_tools: list[str] = field(default_factory=list)

    def validate(self) -> None:
        """Raise ValueError if any enabled tool is outside the agent's tool set."""
        unknown = [t for t in self.enabled_tools if t not in self.ALLOWED_TOOLS]
        if unknown:
            raise ValueError(
                f"unknown tool(s) in enabled_tools: {unknown} "
                f"(allowed: {sorted(self.ALLOWED_TOOLS)})"
            )
