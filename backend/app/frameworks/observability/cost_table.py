"""Pricing constants for per-turn cost estimation (T189).

Rates are USD per 1 000 tokens (LLM) or per 1 000 calls (embeddings).
Update when provider pricing changes; bump version comment with date.

Last updated: 2026-05-28
Source: Anthropic + Voyage published pricing.
"""

from __future__ import annotations

# claude-sonnet-4-6  (input / output per 1k tokens)
ANTHROPIC_INPUT_PER_1K: float = 0.003
ANTHROPIC_OUTPUT_PER_1K: float = 0.015

# Embedding cost per 1 000 API calls (each call embeds one batch)
# voyage-3: $0.00006 / 1k tokens; approx $0.006 per 1k single-text calls
EMBEDDING_COST_PER_1K_CALLS: dict[str, float] = {
    "voyage": 0.006,
    "cohere": 0.0001,   # embed-english-v3.0 batch
    "openai": 0.0001,   # text-embedding-3-large
}


def estimate_turn_cost(
    *,
    llm_in_tokens: int,
    llm_out_tokens: int,
    embedding_calls: int,
    embedding_provider: str = "voyage",
) -> float:
    """Return estimated USD cost for one chat turn."""
    llm_cost = (llm_in_tokens / 1000) * ANTHROPIC_INPUT_PER_1K + (llm_out_tokens / 1000) * ANTHROPIC_OUTPUT_PER_1K
    emb_rate = EMBEDDING_COST_PER_1K_CALLS.get(embedding_provider, EMBEDDING_COST_PER_1K_CALLS["voyage"])
    emb_cost = (embedding_calls / 1000) * emb_rate
    return llm_cost + emb_cost
