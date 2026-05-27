"""Postgres widget repository owned by Slice D."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, MetaData, String, Table, exists, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.allowed_origin import AllowedOrigin
from app.entities.widget import Widget

_meta = MetaData()
WidgetTable = Table(
    "widgets",
    _meta,
    Column("id", PGUUID(as_uuid=True)),
    Column("tenant_id", PGUUID(as_uuid=True)),
    Column("public_id", String),
    Column("is_enabled", Boolean),
    Column("created_at", DateTime(timezone=True)),
)
AllowedOriginTable = Table(
    "allowed_origins",
    _meta,
    Column("id", PGUUID(as_uuid=True)),
    Column("tenant_id", PGUUID(as_uuid=True)),
    Column("origin", String),
    Column("created_at", DateTime(timezone=True)),
)


class PostgresWidgetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_public_id(self, public_id: str) -> Widget | None:
        row = (
            await self._s.execute(
                select(WidgetTable).where(WidgetTable.c.public_id == public_id)
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        return Widget(
            id=row["id"],
            tenant_id=row["tenant_id"],
            public_id=row["public_id"],
            is_enabled=row["is_enabled"],
            created_at=_as_datetime(row["created_at"]),
        )

    async def is_origin_allowed(self, tenant_id: UUID, origin: str) -> bool:
        query = select(
            exists().where(
                AllowedOriginTable.c.tenant_id == tenant_id,
                AllowedOriginTable.c.origin == origin,
            )
        )
        return bool((await self._s.execute(query)).scalar_one())

    async def list_allowed_origins(self, tenant_id: UUID) -> list[AllowedOrigin]:
        rows = (
            await self._s.execute(
                select(AllowedOriginTable).where(AllowedOriginTable.c.tenant_id == tenant_id)
            )
        ).mappings().all()
        return [
            AllowedOrigin(
                id=row["id"],
                tenant_id=row["tenant_id"],
                origin=row["origin"],
                created_at=_as_datetime(row["created_at"]),
            )
            for row in rows
        ]


def _as_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None
