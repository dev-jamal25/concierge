"""Conversation entity (T065) — Layer 1. Pure dataclass, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class Conversation:
    id: UUID
    tenant_id: UUID
    widget_id: UUID
    visitor_session: str
    escalated_at: datetime | None = None
    escalation_reason: str | None = None
    started_at: datetime | None = None
    last_turn_at: datetime | None = None
