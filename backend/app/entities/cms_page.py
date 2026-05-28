"""CMSPage entity (T069) — Layer 1. Pure dataclass, no I/O.

State machine: draft → published, published → unpublished,
unpublished → published. draft → unpublished is forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CMSPageState(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"


@dataclass(slots=True)
class CMSPage:
    id: UUID
    tenant_id: UUID
    title: str
    body: str
    state: CMSPageState
    slug: str
    published_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
