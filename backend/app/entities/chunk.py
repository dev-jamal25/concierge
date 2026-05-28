"""Chunk entity (T067) — Layer 1. Pure dataclass, no I/O.

Embedding dimension is 1024 — fixed by the chosen provider (see DECISIONS.md #2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class Chunk:
    id: UUID
    tenant_id: UUID
    cms_page_id: UUID
    chunk_index: int
    content: str
    embedding: list[float]  # len == 1024
    metadata: dict = field(default_factory=dict)
    embedded_at: datetime | None = None
