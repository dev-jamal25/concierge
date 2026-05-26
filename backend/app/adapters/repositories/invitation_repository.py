"""PostgresInvitationRepository — implements InvitationRepository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.frameworks.db.models import InvitationModel
from app.use_cases.protocols.invitation_repository import InvitationRecord


def _to_record(row: InvitationModel) -> InvitationRecord:
    return InvitationRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        email=row.email,
        expires_at=row.expires_at,
        accepted_at=row.accepted_at,
    )


class PostgresInvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        email: str,
        token_hash: str,
        expires_at: datetime,
        created_by: UUID,
    ) -> InvitationRecord:
        row = InvitationModel(
            tenant_id=tenant_id,
            email=email,
            token_hash=token_hash,
            expires_at=expires_at,
            created_by=created_by,
        )
        self._s.add(row)
        await self._s.flush()
        await self._s.refresh(row)
        return _to_record(row)

    async def get_pending_by_token_hash(self, token_hash: str) -> InvitationRecord | None:
        row = (
            await self._s.execute(
                select(InvitationModel).where(
                    InvitationModel.token_hash == token_hash,
                    InvitationModel.accepted_at.is_(None),
                    InvitationModel.expires_at > func.now(),
                )
            )
        ).scalar_one_or_none()
        return _to_record(row) if row else None

    async def mark_accepted(self, invitation_id: UUID) -> None:
        await self._s.execute(
            update(InvitationModel)
            .where(InvitationModel.id == invitation_id)
            .values(accepted_at=func.now())
        )
