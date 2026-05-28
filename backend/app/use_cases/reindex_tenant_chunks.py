"""ReindexTenantChunksUseCase (T079) — Layer 2.

Active chunker is selected via the CHUNKER env var (default: paragraph_aware).
Variants live in app/use_cases/_chunkers/ (T181 bake-off).

Called on publish and re-publish. On unpublish, caller deletes chunks via
chunk_repo.delete_by_page without re-embedding.
"""

from __future__ import annotations

import importlib
import os
import uuid
from dataclasses import dataclass
from uuid import UUID

from app.entities.chunk import Chunk
from app.use_cases.protocols.chunk_repository import ChunkRepository
from app.use_cases.protocols.embedding_client import EmbeddingClient

_CHUNKER_VARIANTS = {"fixed_500", "paragraph_aware", "header_first"}
_DEFAULT_CHUNKER = "paragraph_aware"


def _load_chunker(name: str | None = None):
    variant = (name or os.environ.get("CHUNKER", _DEFAULT_CHUNKER)).strip()
    if variant not in _CHUNKER_VARIANTS:
        raise ValueError(f"Unknown CHUNKER variant '{variant}'; choose from {_CHUNKER_VARIANTS}")
    module = importlib.import_module(f"app.use_cases._chunkers.{variant}")
    return module.chunk


def _chunk_text(body: str) -> list[str]:
    return _load_chunker()(body)


@dataclass
class ReindexResult:
    deleted: int
    inserted: int


class ReindexTenantChunksUseCase:
    def __init__(
        self,
        chunk_repo: ChunkRepository,
        embedding_client: EmbeddingClient,
    ) -> None:
        self._chunks = chunk_repo
        self._embedder = embedding_client

    async def execute(
        self,
        *,
        cms_page_id: UUID,
        tenant_id: UUID,
        body: str,
    ) -> ReindexResult:
        deleted = await self._chunks.delete_by_page(
            cms_page_id=cms_page_id, tenant_id=tenant_id
        )

        texts = _chunk_text(body)
        if not texts:
            return ReindexResult(deleted=deleted, inserted=0)

        vectors = await self._embedder.embed(texts)

        chunks = [
            Chunk(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                cms_page_id=cms_page_id,
                chunk_index=i,
                content=text,
                embedding=vector,
            )
            for i, (text, vector) in enumerate(zip(texts, vectors))
        ]

        await self._chunks.create_many(chunks)
        return ReindexResult(deleted=deleted, inserted=len(chunks))
