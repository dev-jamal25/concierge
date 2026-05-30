"""ConversationRepository protocol (T022) — Layer 2 interface.

Owner B publishes this seam. All queries are tenant-scoped; RLS enforces at DB.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.entities.conversation import Conversation


class ConversationRepository(Protocol):
    async def create(
        self,
        *,
        tenant_id: UUID,
        widget_id: UUID,
        visitor_session: str,
        conversation_id: UUID | None = None,
    ) -> Conversation: ...

    async def get(self, conversation_id: UUID, tenant_id: UUID) -> Conversation | None: ...

    async def update_escalation(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        reason: str,
    ) -> Conversation: ...
