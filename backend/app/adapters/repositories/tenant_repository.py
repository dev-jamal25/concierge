"""PostgresTenantRepository (T111) — implements TenantRepository.

Defence-in-depth: every query is tenant-scoped at the SQL layer; RLS at the DB
layer is the wall behind it. tenant_admin (concierge_app session) sees only its
own tenant; tenant_manager (concierge_manager session) reads tenant metadata +
provisioning rows, never visitor content (enforced by role grants, not here).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.allowed_origin import AllowedOrigin
from app.entities.tenant import Tenant, TenantPlan, TenantStatus
from app.frameworks.db.models import (
    AllowedOriginModel,
    TenantModel,
)


def _to_tenant(row: TenantModel) -> Tenant:
    return Tenant(
        id=row.id,
        slug=row.slug,
        display_name=row.display_name,
        plan=TenantPlan(row.plan),
        status=TenantStatus(row.status),
        persona_config=row.persona_config,
        theme_config=row.theme_config,
        guardrail_config=row.guardrail_config,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_origin(row: AllowedOriginModel) -> AllowedOrigin:
    return AllowedOrigin(
        id=row.id, tenant_id=row.tenant_id, origin=row.origin, created_at=row.created_at
    )


class PostgresTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        slug: str,
        display_name: str,
        plan: str = "poc",
        persona_config: dict | None = None,
        theme_config: dict | None = None,
        guardrail_config: dict | None = None,
    ) -> Tenant:
        row = TenantModel(
            slug=slug,
            display_name=display_name,
            plan=plan,
            persona_config=persona_config or {},
            theme_config=theme_config or {},
            guardrail_config=guardrail_config or {},
        )
        self._s.add(row)
        await self._s.flush()
        await self._s.refresh(row)
        return _to_tenant(row)

    async def get(self, tenant_id: UUID) -> Tenant | None:
        row = await self._s.get(TenantModel, tenant_id)
        return _to_tenant(row) if row else None

    async def get_by_slug(self, slug: str) -> Tenant | None:
        row = (
            await self._s.execute(select(TenantModel).where(TenantModel.slug == slug))
        ).scalar_one_or_none()
        return _to_tenant(row) if row else None

    async def list(self) -> list[Tenant]:
        rows = (await self._s.execute(select(TenantModel))).scalars().all()
        return [_to_tenant(r) for r in rows]

    async def update(self, tenant_id: UUID, **changes: object) -> Tenant:
        await self._s.execute(
            update(TenantModel).where(TenantModel.id == tenant_id).values(**changes)
        )
        row = await self._s.get(TenantModel, tenant_id)
        assert row is not None
        return _to_tenant(row)

    async def set_status(self, tenant_id: UUID, status: TenantStatus) -> None:
        await self._s.execute(
            update(TenantModel).where(TenantModel.id == tenant_id).values(status=status.value)
        )

    async def delete(self, tenant_id: UUID) -> None:
        # ON DELETE CASCADE removes all tenant-scoped rows (PG store erasure).
        await self._s.execute(delete(TenantModel).where(TenantModel.id == tenant_id))

    async def add_allowed_origin(self, tenant_id: UUID, origin: str) -> AllowedOrigin:
        row = AllowedOriginModel(tenant_id=tenant_id, origin=origin)
        self._s.add(row)
        await self._s.flush()
        await self._s.refresh(row)
        return _to_origin(row)

    async def list_allowed_origins(self, tenant_id: UUID) -> list[AllowedOrigin]:
        rows = (
            await self._s.execute(
                select(AllowedOriginModel).where(AllowedOriginModel.tenant_id == tenant_id)
            )
        ).scalars().all()
        return [_to_origin(r) for r in rows]

    async def create_widget(self, tenant_id: UUID, public_id: str) -> None:
        # widgets table is created in migration 003 (Owner D's entity, Owner A seeds the row).
        await self._s.execute(
            insert(WidgetTable).values(tenant_id=tenant_id, public_id=public_id)
        )


# Lightweight Core table handle for widgets (avoids importing Owner D's ORM model).
from sqlalchemy import Column, MetaData, String, Table  # noqa: E402
from sqlalchemy.dialects.postgresql import UUID as PGUUID  # noqa: E402

_widget_meta = MetaData()
WidgetTable = Table(
    "widgets",
    _widget_meta,
    Column("tenant_id", PGUUID(as_uuid=True)),
    Column("public_id", String),
)
