"""AllowedOrigin entity (T106) — Layer 1. Pure dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class AllowedOrigin:
    id: UUID
    tenant_id: UUID
    origin: str
    created_at: datetime | None = None
