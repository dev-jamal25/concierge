"""ChunkRepository protocol (T023) — Layer 2 interface.

Owner B publishes this seam. QueryChunks filters at query time (NOT post-filter)
using WHERE tenant_id = :tenant_id AND cms_pages.state = 'published'.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.entities.chunk import Chunk


class ChunkRepository(Protocol):
    async def create_many(self, chunks: list[Chunk]) -> list[Chunk]: ...

    async def query(
        self,
        tenant_id: UUID,
        embedding: list[float],
        limit: int = 20,
    ) -> list[Chunk]:
        """ANN search filtered at query time by tenant_id and published state."""
        ...

    async def delete_by_page(self, cms_page_id: UUID, tenant_id: UUID) -> int:
        """Delete all chunks for a page. Returns count deleted."""
        ...
