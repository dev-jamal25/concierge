"""PublishCMSPageUseCase (T078) — Layer 2.

Manages the CMS page state machine and triggers chunk reindexing:
  draft       → published   : reindex chunks
  published   → unpublished : delete chunks
  unpublished → published   : reindex chunks
  draft       → unpublished : FORBIDDEN (raises ValueError)
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.cms_page import CMSPage, CMSPageState
from app.frameworks.db.models import CMSPageModel
from app.use_cases.reindex_tenant_chunks import ReindexTenantChunksUseCase


def _to_entity(row: CMSPageModel) -> CMSPage:
    return CMSPage(
        id=row.id,
        tenant_id=row.tenant_id,
        title=row.title,
        body=row.body,
        state=CMSPageState(row.state),
        slug=row.slug,
        published_at=row.published_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PublishCMSPageUseCase:
    def __init__(
        self,
        session: AsyncSession,
        reindex: ReindexTenantChunksUseCase,
    ) -> None:
        self._session = session
        self._reindex = reindex

    async def publish(self, *, cms_page_id: UUID, tenant_id: UUID) -> CMSPage:
        row = await self._get(cms_page_id, tenant_id)
        current = CMSPageState(row.state)

        if current == CMSPageState.PUBLISHED:
            return _to_entity(row)

        if current == CMSPageState.DRAFT:
            pass  # draft → published is allowed
        elif current == CMSPageState.UNPUBLISHED:
            pass  # unpublished → published is allowed

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(CMSPageModel)
            .where(CMSPageModel.id == cms_page_id, CMSPageModel.tenant_id == tenant_id)
            .values(state="published", published_at=now, updated_at=now)
        )
        await self._session.flush()

        await self._reindex.execute(
            cms_page_id=cms_page_id,
            tenant_id=tenant_id,
            body=row.body,
        )

        updated = await self._get(cms_page_id, tenant_id)
        return _to_entity(updated)

    async def unpublish(self, *, cms_page_id: UUID, tenant_id: UUID) -> CMSPage:
        row = await self._get(cms_page_id, tenant_id)
        current = CMSPageState(row.state)

        if current == CMSPageState.DRAFT:
            raise ValueError("Cannot unpublish a draft page. Publish it first.")

        if current == CMSPageState.UNPUBLISHED:
            return _to_entity(row)

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(CMSPageModel)
            .where(CMSPageModel.id == cms_page_id, CMSPageModel.tenant_id == tenant_id)
            .values(state="unpublished", updated_at=now)
        )
        await self._session.flush()

        # Delete chunks; they'll be re-created on re-publish
        from app.use_cases.protocols.chunk_repository import ChunkRepository
        # chunk deletion done via the reindex use case's delete_by_page
        await self._reindex._chunks.delete_by_page(
            cms_page_id=cms_page_id, tenant_id=tenant_id
        )

        updated = await self._get(cms_page_id, tenant_id)
        return _to_entity(updated)

    async def _get(self, cms_page_id: UUID, tenant_id: UUID) -> CMSPageModel:
        result = await self._session.execute(
            select(CMSPageModel).where(
                CMSPageModel.id == cms_page_id,
                CMSPageModel.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(f"CMS page {cms_page_id} not found for tenant {tenant_id}")
        return row
