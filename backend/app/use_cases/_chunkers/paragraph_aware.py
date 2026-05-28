"""Paragraph-aware chunker: 400-token target, 50-token overlap, 600-token hard cap (T181).

Bake-off variant 2 — the existing baseline from reindex_tenant_chunks.py,
extracted as a standalone module so bake-off can swap implementations.
"""

from __future__ import annotations

_TARGET_TOKENS = 400
_OVERLAP_TOKENS = 50
_HARD_CAP_TOKENS = 600
_CHARS_PER_TOKEN = 4


def _token_estimate(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def chunk(body: str) -> list[str]:
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

    for para in paragraphs:
        para_tokens = _token_estimate(para)

        if window_tokens + para_tokens > _HARD_CAP_TOKENS and window:
            chunks.append("\n\n".join(window))
            overlap_buf: list[str] = []
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
