"""CaptureLeadUseCase (T075) — Layer 2.

Schema-validates visitor-provided fields, enforces rate limits via the
repository, and persists the lead. Returns success or rate_limited status.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.repositories.lead_repository import RateLimitExceeded
from app.entities.lead import Lead
from app.use_cases.protocols.lead_repository import LeadRepository


@dataclass
class CaptureLeadResult:
    success: bool
    lead: Lead | None
    status: str  # "captured" | "rate_limited_window" | "rate_limited_lifetime"


class CaptureLeadUseCase:
    def __init__(self, lead_repo: LeadRepository) -> None:
        self._leads = lead_repo

    async def execute(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        visitor_session: str,
        name: str | None,
        contact: str,
        intent: str,
    ) -> CaptureLeadResult:
        if not contact or not intent:
            return CaptureLeadResult(success=False, lead=None, status="invalid_input")

        try:
            lead = await self._leads.capture(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                visitor_session=visitor_session,
                name=name,
                contact=contact,
                intent=intent,
            )
            return CaptureLeadResult(success=True, lead=lead, status="captured")
        except RateLimitExceeded as exc:
            reason = str(exc)
            status = "rate_limited_window" if "window" in reason else "rate_limited_lifetime"
            return CaptureLeadResult(success=False, lead=None, status=status)
