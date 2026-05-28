"""Fixed-size chunker: 500-token windows, no overlap, no heading awareness (T181).

Bake-off variant 1 — the naïve floor. Any structured chunker must beat this.
"""

from __future__ import annotations

_CHARS_PER_TOKEN = 4
_WINDOW_TOKENS = 500


def chunk(body: str) -> list[str]:
    """Split body into 500-token fixed-size windows with no overlap."""
    window_chars = _WINDOW_TOKENS * _CHARS_PER_TOKEN
    chunks: list[str] = []
    start = 0
    while start < len(body):
        end = start + window_chars
        chunks.append(body[start:end].strip())
        start = end
    return [c for c in chunks if c]
