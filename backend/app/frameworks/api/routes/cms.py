"""CMS routes (T089) — /cms/pages CRUD + publish/unpublish.

All endpoints are tenant-scoped via TenantContextMiddleware (JWT → tenant_id).
Write operations trigger async chunk reindexing via PublishCMSPageUseCase.

State machine:
  draft → published   (POST /publish)
  published → unpublished (POST /unpublish)
  unpublished → published (POST /publish)
  draft → unpublished  FORBIDDEN → 409
  DELETE only allowed on draft pages → 409 otherwise
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.embeddings.hosted_embeddings import HostedEmbeddings
from app.adapters.repositories.chunk_repository import PostgresChunkRepository
from app.adapters.repositories.cms_page_repository import PostgresCMSPageRepository
from app.entities.cms_page import CMSPageState
from app.frameworks.api.deps import db_session, get_app_settings, get_current_tenant_id
from app.frameworks.config import Settings
from app.frameworks.db.models import CMSPageModel
from app.use_cases.publish_cms_page import PublishCMSPageUseCase
from app.use_cases.reindex_tenant_chunks import ReindexTenantChunksUseCase

router = APIRouter(prefix="/cms", tags=["cms"])


# --- Pydantic schemas (per api.openapi.yaml) ---


class CMSPageOut(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    body: str
    state: str
    slug: str
    published_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CMSPageCreate(BaseModel):
    title: str
    body: str
    slug: str


class CMSPageUpdate(BaseModel):
    title: str | None = None
    body: str | None = None


# --- Helpers ---


def _build_publish_uc(session: AsyncSession, settings: Settings) -> PublishCMSPageUseCase:
    cms_repo = PostgresCMSPageRepository(session)
    chunk_repo = PostgresChunkRepository(session)
    embedder = HostedEmbeddings(
        provider=settings.embedding_provider,
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
    )
    reindex = ReindexTenantChunksUseCase(chunk_repo, embedder)
    return PublishCMSPageUseCase(cms_repo, chunk_repo, reindex)


def _page_out(row: CMSPageModel) -> CMSPageOut:
    return CMSPageOut(
        id=row.id,
        tenant_id=row.tenant_id,
        title=row.title,
        body=row.body,
        state=row.state,
        slug=row.slug,
        published_at=row.published_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# --- Routes ---


@router.get("/pages", response_model=list[CMSPageOut])
async def list_pages(
    state: str | None = None,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
) -> list[CMSPageOut]:
    tenant_id = UUID(tenant_id_str)
    stmt = select(CMSPageModel).where(CMSPageModel.tenant_id == tenant_id)
    if state is not None:
        stmt = stmt.where(CMSPageModel.state == state)
    stmt = stmt.order_by(CMSPageModel.created_at.desc())
    result = await session.execute(stmt)
    return [_page_out(r) for r in result.scalars().all()]


@router.post("/pages", response_model=CMSPageOut, status_code=status.HTTP_201_CREATED)
async def create_page(
    body: CMSPageCreate,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
) -> CMSPageOut:
    tenant_id = UUID(tenant_id_str)
    row = CMSPageModel(
        tenant_id=tenant_id,
        title=body.title,
        body=body.body,
        slug=body.slug,
        state=CMSPageState.DRAFT.value,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return _page_out(row)


@router.get("/pages/{page_id}", response_model=CMSPageOut)
async def get_page(
    page_id: UUID,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
) -> CMSPageOut:
    tenant_id = UUID(tenant_id_str)
    result = await session.execute(
        select(CMSPageModel).where(
            CMSPageModel.id == page_id,
            CMSPageModel.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CMS page not found")
    return _page_out(row)


@router.put("/pages/{page_id}", response_model=CMSPageOut)
async def update_page(
    page_id: UUID,
    body: CMSPageUpdate,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
) -> CMSPageOut:
    tenant_id = UUID(tenant_id_str)
    result = await session.execute(
        select(CMSPageModel).where(
            CMSPageModel.id == page_id,
            CMSPageModel.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CMS page not found")

    if body.title is not None:
        row.title = body.title
    if body.body is not None:
        row.body = body.body
    row.updated_at = datetime.now(timezone.utc)

    await session.flush()
    await session.refresh(row)
    return _page_out(row)


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(
    page_id: UUID,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
) -> None:
    tenant_id = UUID(tenant_id_str)
    result = await session.execute(
        select(CMSPageModel).where(
            CMSPageModel.id == page_id,
            CMSPageModel.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CMS page not found")
    if row.state != CMSPageState.DRAFT.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only draft pages can be deleted. Unpublish first.",
        )
    await session.delete(row)


@router.post("/pages/{page_id}/publish", status_code=status.HTTP_202_ACCEPTED)
async def publish_page(
    page_id: UUID,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    tenant_id = UUID(tenant_id_str)
    uc = _build_publish_uc(session, settings)
    try:
        await uc.publish(cms_page_id=page_id, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"status": "accepted"}


@router.post("/pages/{page_id}/unpublish", status_code=status.HTTP_202_ACCEPTED)
async def unpublish_page(
    page_id: UUID,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    tenant_id = UUID(tenant_id_str)
    uc = _build_publish_uc(session, settings)
    try:
        await uc.unpublish(cms_page_id=page_id, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"status": "accepted"}
