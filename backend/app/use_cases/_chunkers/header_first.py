"""Header-first recursive chunker (T181).

Bake-off variant 3: split on Markdown headings, then recursively on \\n\\n
to fit 400/50/600 bounds. Each child chunk is prepended with its full
heading path (e.g. "H1 > H2 > H3\\n\\n<body>") so the embedder carries
structural context.
"""

from __future__ import annotations

import re

_TARGET_TOKENS = 400
_OVERLAP_TOKENS = 50
_HARD_CAP_TOKENS = 600
_CHARS_PER_TOKEN = 4

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)", re.MULTILINE)


def _token_estimate(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def _split_into_sections(body: str) -> list[tuple[str, str]]:
    """Return [(heading_path, section_body), ...] by splitting on # headings.

    heading_path is the H1 > H2 > ... breadcrumb; section_body is the text
    under that heading (not including the heading line itself).
    """
    lines = body.splitlines(keepends=True)
    sections: list[tuple[str, str]] = []
    heading_stack: list[str] = []
    current_lines: list[str] = []
    current_path = ""

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            if current_lines:
                sections.append((current_path, "".join(current_lines).strip()))
                current_lines = []
            level = len(m.group(1))
            title = m.group(2).strip()
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(title)
            current_path = " > ".join(heading_stack)
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_path, "".join(current_lines).strip()))

    return [(p, b) for p, b in sections if b]


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]


def _merge_paragraphs(paragraphs: list[str], heading_prefix: str) -> list[str]:
    """Merge paragraphs into token-bounded chunks, prepending the heading path."""
    chunks: list[str] = []
    window: list[str] = []
    window_tokens = 0

    def _flush(w: list[str]) -> str:
        body = "\n\n".join(w)
        return f"{heading_prefix}\n\n{body}" if heading_prefix else body

    for para in paragraphs:
        para_tokens = _token_estimate(para)

        if window_tokens + para_tokens > _HARD_CAP_TOKENS and window:
            chunks.append(_flush(window))
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
            chunks.append(_flush(window))
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
        chunks.append(_flush(window))

    return chunks


def chunk(body: str) -> list[str]:
    """Split body heading-first, then paragraph-merge each section."""
    sections = _split_into_sections(body)
    if not sections:
        return _merge_paragraphs(_split_paragraphs(body), "")

    result: list[str] = []
    for heading_path, section_body in sections:
        paragraphs = _split_paragraphs(section_body)
        if not paragraphs:
            continue
        result.extend(_merge_paragraphs(paragraphs, heading_path))
    return [c for c in result if c.strip()]
