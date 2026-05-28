"""PostgresCMSPageRepository — Layer 3 adapter implementing CMSPageRepository."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.cms_page import CMSPage, CMSPageState
from app.frameworks.db.models import CMSPageModel


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


class PostgresCMSPageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, cms_page_id: UUID, tenant_id: UUID) -> CMSPage | None:
        result = await self._session.execute(
            select(CMSPageModel).where(
                CMSPageModel.id == cms_page_id,
                CMSPageModel.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        return _to_entity(row) if row is not None else None

    async def update_state(
        self,
        cms_page_id: UUID,
        tenant_id: UUID,
        *,
        state: CMSPageState,
        published_at: datetime | None = None,
    ) -> CMSPage:
        values: dict = {
            "state": state.value,
            "updated_at": datetime.now(timezone.utc),
        }
        if published_at is not None:
            values["published_at"] = published_at

        await self._session.execute(
            update(CMSPageModel)
            .where(
                CMSPageModel.id == cms_page_id,
                CMSPageModel.tenant_id == tenant_id,
            )
            .values(**values)
        )
        await self._session.flush()

        result = await self._session.execute(
            select(CMSPageModel).where(
                CMSPageModel.id == cms_page_id,
                CMSPageModel.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one()
        return _to_entity(row)
