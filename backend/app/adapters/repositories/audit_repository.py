"""PostgresAuditRepository (T021 impl) — implements AuditRepository. Append-only.

Runs under the concierge_manager session (the only role with INSERT/SELECT on
audit_entries). UPDATE/DELETE are revoked at the DB layer, so the log is immutable.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.audit_entry import AuditEntry, AuditOutcome
from app.frameworks.db.models import AuditEntryModel


def _to_entry(row: AuditEntryModel) -> AuditEntry:
    return AuditEntry(
        id=row.id,
        action=row.action,
        outcome=AuditOutcome(row.outcome),
        actor_user_id=row.actor_user_id,
        target_tenant_id=row.target_tenant_id,
        details=row.details,
        created_at=row.created_at,
    )


class PostgresAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def log(
        self,
        *,
        action: str,
        outcome: AuditOutcome,
        actor_user_id: UUID | None = None,
        target_tenant_id: UUID | None = None,
        details: dict | None = None,
    ) -> None:
        await self._s.execute(
            insert(AuditEntryModel).values(
                action=action,
                outcome=outcome.value,
                actor_user_id=actor_user_id,
                target_tenant_id=target_tenant_id,
                details=details or {},
            )
        )

    async def list_all(self) -> list[AuditEntry]:
        rows = (
            await self._s.execute(
                select(AuditEntryModel).order_by(AuditEntryModel.created_at.desc())
            )
        ).scalars().all()
        return [_to_entry(r) for r in rows]
