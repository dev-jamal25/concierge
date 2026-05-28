"""EscalateUseCase (T076) — Layer 2.

Flags a conversation for human follow-up. Reason may be:
  visitor_request   — visitor explicitly asked to speak to a human
  llm_unavailable   — LLM/embedding timed out after retries
  tool_loop_cap     — agent hit max_iterations without resolving
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from app.entities.conversation import Conversation
from app.use_cases.protocols.conversation_repository import ConversationRepository

EscalationReason = Literal["visitor_request", "llm_unavailable", "tool_loop_cap"]


class EscalateUseCase:
    def __init__(self, conversation_repo: ConversationRepository) -> None:
        self._conversations = conversation_repo

    async def execute(
        self,
        *,
        conversation_id: UUID,
        tenant_id: UUID,
        reason: EscalationReason,
    ) -> Conversation:
        return await self._conversations.update_escalation(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            reason=reason,
        )
