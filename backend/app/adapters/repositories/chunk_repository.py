"""PostgresChunkRepository (T071) — implements ChunkRepository.

Critical constraint (FR-017): the tenant_id filter is applied AT QUERY TIME
inside the SQL WHERE clause — NEVER as a post-filter after the ANN scan.
The composite plan (B-tree on tenant_id + HNSW on embedding) is what makes
this safe; EXPLAIN ANALYZE in the integration test verifies the planner honours it.

Only chunks whose cms_page is in state='published' are returned.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.chunk import Chunk
from app.frameworks.db.models import ChunkModel, CMSPageModel


def _to_entity(row: ChunkModel) -> Chunk:
    return Chunk(
        id=row.id,
        tenant_id=row.tenant_id,
        cms_page_id=row.cms_page_id,
        chunk_index=row.chunk_index,
        content=row.content,
        embedding=list(row.embedding),
        metadata=row.metadata_,
        embedded_at=row.embedded_at,
    )


class PostgresChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_many(self, chunks: list[Chunk]) -> list[Chunk]:
        rows = [
            ChunkModel(
                id=c.id,
                tenant_id=c.tenant_id,
                cms_page_id=c.cms_page_id,
                chunk_index=c.chunk_index,
                content=c.content,
                embedding=c.embedding,
                metadata_=c.metadata,
            )
            for c in chunks
        ]
        self._s.add_all(rows)
        await self._s.flush()
        return [_to_entity(r) for r in rows]

    async def query(
        self,
        tenant_id: UUID,
        embedding: list[float],
        limit: int = 20,
    ) -> list[Chunk]:
        # Filter at query time: tenant_id + published state in the WHERE clause.
        # The planner uses ix_chunks_tenant then ix_chunks_embedding_hnsw.
        stmt = (
            select(ChunkModel)
            .join(CMSPageModel, ChunkModel.cms_page_id == CMSPageModel.id)
            .where(
                ChunkModel.tenant_id == tenant_id,
                CMSPageModel.state == "published",
            )
            .order_by(ChunkModel.embedding.op("<=>") (embedding))
            .limit(limit)
        )
        result = await self._s.execute(stmt)
        return [_to_entity(r) for r in result.scalars().all()]

    async def delete_by_page(self, cms_page_id: UUID, tenant_id: UUID) -> int:
        result = await self._s.execute(
            delete(ChunkModel)
            .where(
                ChunkModel.cms_page_id == cms_page_id,
                ChunkModel.tenant_id == tenant_id,
            )
            .returning(ChunkModel.id)
        )
        return len(result.fetchall())
