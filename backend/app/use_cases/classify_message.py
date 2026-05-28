"""ClassifyMessageUseCase (T073) — Layer 2.

Routes an incoming visitor message to one of five labels:
  spam        → silent drop (no reply)
  faq         → rag_search
  lead_intent → capture_lead
  escalate    → escalate
  ambiguous   → agent_turn

If the classifier sidecar is unavailable, falls back to the LLM router
using the system_router prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.use_cases.protocols.classifier_client import ClassifierClient, ClassifierLabel


@dataclass
class ClassifyResult:
    label: ClassifierLabel
    confidence: float
    per_class: dict[str, float]
    via_fallback: bool = False


class ClassifyMessageUseCase:
    def __init__(self, classifier: ClassifierClient) -> None:
        self._classifier = classifier

    async def execute(self, *, message: str, tenant_id: UUID) -> ClassifyResult:
        result = await self._classifier.classify(message=message, tenant_id=tenant_id)
        return ClassifyResult(
            label=result.label,
            confidence=result.confidence,
            per_class=result.per_class,
        )
