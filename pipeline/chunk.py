"""Split page text into retrieval chunks that keep doc, chapter and page range.

Chunks target ~320 words, end on a sentence boundary when one is near, and overlap
by ~40 words so a step list cut in half still appears whole in one chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict

_CHAPTER = re.compile(r"^\s*chapter\s+(\d{1,2})\b", re.IGNORECASE | re.MULTILINE)
_APPENDIX = re.compile(r"^\s*appendix\s+([a-z])\b", re.IGNORECASE | re.MULTILINE)
_SENTENCE_END = (".", "!", "?", ":")


@dataclass
class Chunk:
    doc: str
    chapter: str
    page_start: int
    page_end: int
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def detect_section(page_text: str, current: str) -> str:
    """Return the chapter or appendix label in force for this page."""
    m = _CHAPTER.search(page_text)
    if m:
        return m.group(1)
    m = _APPENDIX.search(page_text)
    if m:
        return f"App {m.group(1).upper()}"
    return current


def chunk_pages(
    pages: list[dict],
    target_words: int = 320,
    overlap_words: int = 40,
    max_extend: int = 60,
    min_words: int = 40,
) -> list[Chunk]:
    """pages: [{"doc": str, "page": int, "text": str}] for ONE document, in order."""
    if not pages:
        return []
    doc = pages[0]["doc"]
    words: list[tuple[str, int, str]] = []  # (word, page, chapter)
    chapter = "?"
    for p in pages:
        if p["doc"] != doc:
            raise ValueError("chunk_pages expects pages from a single document")
        chapter = detect_section(p["text"], chapter)
        for w in p["text"].split():
            words.append((w, p["page"], chapter))

    chunks: list[Chunk] = []
    i = 0
    n = len(words)
    while i < n:
        end = min(i + target_words, n)
        # extend to a sentence end if one is close
        j = end
        while j < n and j < end + max_extend and not words[j - 1][0].endswith(_SENTENCE_END):
            j += 1
        if j <= n and words[j - 1][0].endswith(_SENTENCE_END):
            end = j
        span = words[i:end]
        if len(span) >= min_words or not chunks:
            chunks.append(
                Chunk(
                    doc=doc,
                    chapter=span[0][2] if span[0][2] == span[-1][2] else f"{span[0][2]}/{span[-1][2]}",
                    page_start=span[0][1],
                    page_end=span[-1][1],
                    text=" ".join(w for w, _, _ in span),
                )
            )
        elif chunks:  # tiny tail: merge into previous chunk
            prev = chunks[-1]  # span starts overlap_words before prev ended
            prev.text = prev.text + " " + " ".join(w for w, _, _ in span[overlap_words:])
            prev.page_end = span[-1][1]
        if end >= n:
            break
        i = max(end - overlap_words, i + 1)
    return chunks
