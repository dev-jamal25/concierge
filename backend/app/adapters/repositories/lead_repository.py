"""PostgresLeadRepository (T072) — implements LeadRepository.

Rate-limiting enforced here: ≤1 lead per visitor_session per 60 seconds,
≤5 leads per session lifetime. Excess attempts raise RateLimitExceeded.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.lead import Lead
from app.frameworks.db.models import LeadModel
from app.use_cases.protocols.lead_repository import RateLimitExceeded

__all__ = ["PostgresLeadRepository", "RateLimitExceeded"]


def _to_entity(row: LeadModel) -> Lead:
    return Lead(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_id=row.conversation_id,
        contact=row.contact,
        intent=row.intent,
        name=row.name,
        created_at=row.created_at,
    )


class PostgresLeadRepository:
    _PER_SESSION_WINDOW_SECONDS = 60
    _PER_SESSION_LIFETIME_MAX = 5

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def capture(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        visitor_session: str,
        name: str | None,
        contact: str,
        intent: str,
    ) -> Lead:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=self._PER_SESSION_WINDOW_SECONDS)

        # Rate-limit check: ≤1 in last 60s
        recent = await self._s.scalar(
            select(func.count())
            .select_from(LeadModel)
            .where(
                LeadModel.tenant_id == tenant_id,
                LeadModel.conversation_id == conversation_id,
                LeadModel.created_at >= window_start,
            )
        )
        if recent and recent >= 1:
            raise RateLimitExceeded("rate_limit_window")

        # Rate-limit check: ≤5 lifetime per session
        lifetime = await self.count_by_session(tenant_id, visitor_session)
        if lifetime >= self._PER_SESSION_LIFETIME_MAX:
            raise RateLimitExceeded("rate_limit_lifetime")

        row = LeadModel(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            name=name,
            contact=contact,
            intent=intent,
        )
        self._s.add(row)
        await self._s.flush()
        await self._s.refresh(row)
        return _to_entity(row)

    async def list(
        self,
        tenant_id: UUID,
        since: str | None = None,
    ) -> list[Lead]:
        stmt = (
            select(LeadModel)
            .where(LeadModel.tenant_id == tenant_id)
            .order_by(LeadModel.created_at.desc())
        )
        if since:
            stmt = stmt.where(LeadModel.created_at >= since)
        result = await self._s.execute(stmt)
        return [_to_entity(r) for r in result.scalars().all()]

    async def count_by_session(self, tenant_id: UUID, visitor_session: str) -> int:
        # Joins conversations to scope by visitor_session
        from app.frameworks.db.models import ConversationModel

        count = await self._s.scalar(
            select(func.count())
            .select_from(LeadModel)
            .join(ConversationModel, LeadModel.conversation_id == ConversationModel.id)
            .where(
                LeadModel.tenant_id == tenant_id,
                ConversationModel.visitor_session == visitor_session,
            )
        )
        return count or 0
