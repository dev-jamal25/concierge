"""Leads routes (T119) — GET /leads and GET /leads/export.

Tenant-scoped via TenantContextMiddleware. Supports optional `since` filter.
Export returns CSV for CRM integration.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repositories.lead_repository import PostgresLeadRepository
from app.frameworks.api.deps import db_session, get_current_tenant_id

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadOut(BaseModel):
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    name: str | None = None
    contact: str
    intent: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[LeadOut])
async def list_leads(
    since: datetime | None = None,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
) -> list[LeadOut]:
    tenant_id = UUID(tenant_id_str)
    repo = PostgresLeadRepository(session)
    since_str = since.isoformat() if since else None
    leads = await repo.list(tenant_id, since=since_str)
    return [
        LeadOut(
            id=lead.id,
            tenant_id=lead.tenant_id,
            conversation_id=lead.conversation_id,
            name=lead.name,
            contact=lead.contact,
            intent=lead.intent,
            created_at=lead.created_at,
        )
        for lead in leads
    ]


@router.get("/export")
async def export_leads(
    since: datetime | None = None,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
) -> StreamingResponse:
    tenant_id = UUID(tenant_id_str)
    repo = PostgresLeadRepository(session)
    since_str = since.isoformat() if since else None
    leads = await repo.list(tenant_id, since=since_str)

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["id", "tenant_id", "conversation_id", "name", "contact", "intent", "created_at"],
    )
    writer.writeheader()
    for lead in leads:
        writer.writerow(
            {
                "id": str(lead.id),
                "tenant_id": str(lead.tenant_id),
                "conversation_id": str(lead.conversation_id),
                "name": lead.name or "",
                "contact": lead.contact,
                "intent": lead.intent,
                "created_at": lead.created_at.isoformat() if lead.created_at else "",
            }
        )
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )
