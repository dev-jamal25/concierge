"""InviteAdminUseCase (T109).

Creates an invitations row (storing only the token hash) and dispatches the
invitation link via the EmailSender stub. Used during provisioning and when an
admin invites further admins to their tenant. Depends only on protocols.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.use_cases.invitation_tokens import generate_invitation_token
from app.use_cases.protocols.email_sender import EmailSender
from app.use_cases.protocols.invitation_repository import (
    InvitationRecord,
    InvitationRepository,
)


@dataclass(slots=True)
class InviteResult:
    invitation: InvitationRecord
    raw_token: str


class InviteAdminUseCase:
    def __init__(
        self,
        invitations: InvitationRepository,
        emails: EmailSender,
        *,
        ttl_hours: int,
        accept_url_base: str,
    ) -> None:
        self._invitations = invitations
        self._emails = emails
        self._ttl_hours = ttl_hours
        self._accept_url_base = accept_url_base.rstrip("/")

    async def execute(
        self, *, tenant_id: UUID, tenant_name: str, email: str, created_by: UUID
    ) -> InviteResult:
        raw_token, token_hash = generate_invitation_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self._ttl_hours)
        invitation = await self._invitations.create(
            tenant_id=tenant_id,
            email=email,
            token_hash=token_hash,
            expires_at=expires_at,
            created_by=created_by,
        )
        accept_url = f"{self._accept_url_base}/auth/invitations/{raw_token}/accept"
        await self._emails.send_invitation(
            to=email, tenant_name=tenant_name, accept_url=accept_url
        )
        return InviteResult(invitation=invitation, raw_token=raw_token)
