"""Lead entity (T068) — Layer 1. Pure dataclass, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class Lead:
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    contact: str
    intent: str
    name: str | None = None
    created_at: datetime | None = None
