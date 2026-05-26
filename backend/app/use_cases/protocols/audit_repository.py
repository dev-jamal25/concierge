"""AuditRepository protocol (T021) — Layer 2 interface. Append-only."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.entities.audit_entry import AuditEntry, AuditOutcome


class AuditRepository(Protocol):
    async def log(
        self,
        *,
        action: str,
        outcome: AuditOutcome,
        actor_user_id: UUID | None = None,
        target_tenant_id: UUID | None = None,
        details: dict | None = None,
    ) -> None:
        """Append one audit entry. Never updates or deletes."""
        ...

    async def list_all(self) -> list[AuditEntry]:
        """Manager-only: every audit entry, unscoped by tenant."""
        ...
