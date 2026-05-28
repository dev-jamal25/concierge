"""CMSPageRepository protocol — Layer 2 seam for CMS page persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.entities.cms_page import CMSPage, CMSPageState


class CMSPageRepository(Protocol):
    async def get(self, cms_page_id: UUID, tenant_id: UUID) -> CMSPage | None: ...

    async def update_state(
        self,
        cms_page_id: UUID,
        tenant_id: UUID,
        *,
        state: CMSPageState,
        published_at: datetime | None = None,
    ) -> CMSPage: ...
