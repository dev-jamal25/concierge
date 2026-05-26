"""AuditEntry entity (T107) — Layer 1. Pure dataclass.

Append-only record of tenant_manager actions. `target_tenant_id` is intentionally
not a foreign key in the schema so the row survives the tenant it referenced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    FAILURE = "failure"


@dataclass(slots=True)
class AuditEntry:
    id: UUID
    action: str
    outcome: AuditOutcome
    actor_user_id: UUID | None = None
    target_tenant_id: UUID | None = None
    details: dict = field(default_factory=dict)
    created_at: datetime | None = None
