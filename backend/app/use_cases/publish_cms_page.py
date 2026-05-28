"""PublishCMSPageUseCase (T078) — Layer 2.

Manages the CMS page state machine and triggers chunk reindexing:
  draft       → published   : reindex chunks
  published   → unpublished : delete chunks
  unpublished → published   : reindex chunks
  draft       → unpublished : FORBIDDEN (raises ValueError)
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.entities.cms_page import CMSPage, CMSPageState
from app.use_cases.protocols.chunk_repository import ChunkRepository
from app.use_cases.protocols.cms_page_repository import CMSPageRepository
from app.use_cases.reindex_tenant_chunks import ReindexTenantChunksUseCase


class PublishCMSPageUseCase:
    def __init__(
        self,
        cms_pages: CMSPageRepository,
        chunks: ChunkRepository,
        reindex: ReindexTenantChunksUseCase,
    ) -> None:
        self._cms_pages = cms_pages
        self._chunks = chunks
        self._reindex = reindex

    async def publish(self, *, cms_page_id: UUID, tenant_id: UUID) -> CMSPage:
        page = await self._get(cms_page_id, tenant_id)

        if page.state == CMSPageState.PUBLISHED:
            return page

        now = datetime.now(timezone.utc)
        updated = await self._cms_pages.update_state(
            cms_page_id,
            tenant_id,
            state=CMSPageState.PUBLISHED,
            published_at=now,
        )

        await self._reindex.execute(
            cms_page_id=cms_page_id,
            tenant_id=tenant_id,
            body=page.body,
        )

        return updated

    async def unpublish(self, *, cms_page_id: UUID, tenant_id: UUID) -> CMSPage:
        page = await self._get(cms_page_id, tenant_id)

        if page.state == CMSPageState.DRAFT:
            raise ValueError("Cannot unpublish a draft page. Publish it first.")

        if page.state == CMSPageState.UNPUBLISHED:
            return page

        updated = await self._cms_pages.update_state(
            cms_page_id,
            tenant_id,
            state=CMSPageState.UNPUBLISHED,
        )

        await self._chunks.delete_by_page(
            cms_page_id=cms_page_id, tenant_id=tenant_id
        )

        return updated

    async def _get(self, cms_page_id: UUID, tenant_id: UUID) -> CMSPage:
        page = await self._cms_pages.get(cms_page_id, tenant_id)
        if page is None:
            raise ValueError(
                f"CMS page {cms_page_id} not found for tenant {tenant_id}"
            )
        return page
