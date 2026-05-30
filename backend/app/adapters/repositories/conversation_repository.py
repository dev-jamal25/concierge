"""PostgresConversationRepository (T070) — implements ConversationRepository.

Every query is explicitly tenant-scoped (WHERE tenant_id = :tenant_id) as
defence-in-depth behind the RLS wall set by TenantContextMiddleware.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.conversation import Conversation
from app.frameworks.db.models import ConversationModel


def _to_entity(row: ConversationModel) -> Conversation:
    return Conversation(
        id=row.id,
        tenant_id=row.tenant_id,
        widget_id=row.widget_id,
        visitor_session=row.visitor_session,
        escalated_at=row.escalated_at,
        escalation_reason=row.escalation_reason,
        started_at=row.started_at,
        last_turn_at=row.last_turn_at,
    )


class PostgresConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        widget_id: UUID,
        visitor_session: str,
        conversation_id: UUID | None = None,
    ) -> Conversation:
        model_kwargs: dict = {
            "tenant_id": tenant_id,
            "widget_id": widget_id,
            "visitor_session": visitor_session,
        }
        if conversation_id is not None:
            model_kwargs["id"] = conversation_id
        row = ConversationModel(**model_kwargs)
        self._s.add(row)
        await self._s.flush()
        await self._s.refresh(row)
        return _to_entity(row)

    async def get(self, conversation_id: UUID, tenant_id: UUID) -> Conversation | None:
        result = await self._s.execute(
            select(ConversationModel).where(
                ConversationModel.id == conversation_id,
                ConversationModel.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        return _to_entity(row) if row else None

    async def update_escalation(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        reason: str,
    ) -> Conversation:
        now = datetime.now(timezone.utc)
        await self._s.execute(
            update(ConversationModel)
            .where(
                ConversationModel.id == conversation_id,
                ConversationModel.tenant_id == tenant_id,
            )
            .values(escalated_at=now, escalation_reason=reason, last_turn_at=now)
        )
        row = await self._s.get(ConversationModel, conversation_id)
        if row is None:
            raise LookupError(
                f"Conversation {conversation_id} not found after escalation update"
            )
        return _to_entity(row)
