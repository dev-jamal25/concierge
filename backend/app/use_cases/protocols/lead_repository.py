"""LeadRepository protocol (T024) — Layer 2 interface.

Owner B publishes this seam. Rate limiting (≤1/60s, ≤5 lifetime per session)
is enforced inside the adapter implementation, not here.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.entities.lead import Lead


class RateLimitExceeded(Exception):
    """Raised by LeadRepository.capture when a session breaches rate limits."""


class LeadRepository(Protocol):
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
        """Create a lead. Raises RateLimitExceeded if visitor hit the cap."""
        ...

    async def list(
        self,
        tenant_id: UUID,
        since: str | None = None,
    ) -> list[Lead]: ...

    async def count_by_session(self, tenant_id: UUID, visitor_session: str) -> int: ...
