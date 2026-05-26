"""Widget entity owned by Slice D."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Widget:
    id: UUID
    tenant_id: UUID
    public_id: str
    is_enabled: bool
    created_at: datetime | None = None
