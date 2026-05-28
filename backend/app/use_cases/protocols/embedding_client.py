"""EmbeddingClient protocol (T026) — Layer 2 interface.

Owner B publishes this seam. The concrete adapter (HostedEmbeddings) lives in
adapters/embeddings/; provider (Voyage / Cohere / OpenAI) is selected via env.

Vector dimension is 1024 (documented in data-model.md and DECISIONS.md entry 2).
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order."""
        ...
