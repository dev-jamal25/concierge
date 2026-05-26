"""InvitationRepository protocol — Owner A domain aggregate (supports T108/T109/T114).

Not in the original T019-T021 set, but invitations are a distinct Owner A
aggregate (own table, own lifecycle) and SRP argues against folding them into
TenantRepository. The record type is defined here rather than in entities/ to
match plan.md's entity list (which has no Invitation entity).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(slots=True)
class InvitationRecord:
    id: UUID
    tenant_id: UUID
    email: str
    expires_at: datetime
    accepted_at: datetime | None = None


class InvitationRepository(Protocol):
    async def create(
        self,
        *,
        tenant_id: UUID,
        email: str,
        token_hash: str,
        expires_at: datetime,
        created_by: UUID,
    ) -> InvitationRecord: ...

    async def get_pending_by_token_hash(self, token_hash: str) -> InvitationRecord | None:
        """Return an un-accepted, unexpired invitation matching the token hash."""
        ...

    async def mark_accepted(self, invitation_id: UUID) -> None: ...
