"""ClassifierClient protocol (T027) — Layer 2 interface.

Owner C publishes this seam; Owner B's router codes against it (never the
concrete modelserver adapter). Mirrors the wire contract in
`specs/001-concierge-platform/contracts/internal/modelserver.yaml` (`POST /predict`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

ClassifierLabel = Literal["spam", "faq", "lead_intent", "escalate", "ambiguous"]


@dataclass(frozen=True)
class ClassifierResult:
    label: ClassifierLabel
    confidence: float
    per_class: dict[str, float]
    artifact_sha256: str


class ClassifierClient(Protocol):
    async def classify(
        self,
        *,
        message: str,
        tenant_id: UUID,
    ) -> ClassifierResult: ...
