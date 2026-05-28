"""ReindexTenantChunksUseCase (T079) — Layer 2.

Paragraph-aware chunking per research.md #1:
  target 400 tokens, overlap 50 tokens, hard cap 600 tokens.
  Respects heading boundaries (lines starting with #).

Called on publish and re-publish. On unpublish, caller deletes chunks via
chunk_repo.delete_by_page without re-embedding.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from app.entities.chunk import Chunk
from app.use_cases.protocols.chunk_repository import ChunkRepository
from app.use_cases.protocols.embedding_client import EmbeddingClient

_TARGET_TOKENS = 400
_OVERLAP_TOKENS = 50
_HARD_CAP_TOKENS = 600
_CHARS_PER_TOKEN = 4  # rough approximation for plain text


def _token_estimate(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def _chunk_text(body: str) -> list[str]:
    """Split body into paragraph-aware, token-bounded chunks with overlap."""
    paragraphs: list[str] = []
    current: list[str] = []

    for line in body.splitlines(keepends=True):
        if line.startswith("#") and current:
            paragraphs.append("".join(current).strip())
            current = [line]
        elif line.strip() == "" and current:
            paragraphs.append("".join(current).strip())
            current = []
        else:
            current.append(line)
    if current:
        paragraphs.append("".join(current).strip())

    paragraphs = [p for p in paragraphs if p]

    chunks: list[str] = []
    window: list[str] = []
    window_tokens = 0
    overlap_buf: list[str] = []

    for para in paragraphs:
        para_tokens = _token_estimate(para)

        if window_tokens + para_tokens > _HARD_CAP_TOKENS and window:
            chunks.append("\n\n".join(window))
            # keep overlap tail
            overlap_buf = []
            overlap_tokens = 0
            for p in reversed(window):
                t = _token_estimate(p)
                if overlap_tokens + t <= _OVERLAP_TOKENS:
                    overlap_buf.insert(0, p)
                    overlap_tokens += t
                else:
                    break
            window = overlap_buf[:]
            window_tokens = sum(_token_estimate(p) for p in window)

        window.append(para)
        window_tokens += para_tokens

        if window_tokens >= _TARGET_TOKENS:
            chunks.append("\n\n".join(window))
            overlap_buf = []
            overlap_tokens = 0
            for p in reversed(window):
                t = _token_estimate(p)
                if overlap_tokens + t <= _OVERLAP_TOKENS:
                    overlap_buf.insert(0, p)
                    overlap_tokens += t
                else:
                    break
            window = overlap_buf[:]
            window_tokens = sum(_token_estimate(p) for p in window)

    if window:
        chunks.append("\n\n".join(window))

    return [c for c in chunks if c.strip()]


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
