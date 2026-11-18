"""BM25 search over the library (SQLite FTS5). The Swift LibraryStore mirrors
`build_match_query` exactly, so training retrieval and on device retrieval agree.

    python -m pipeline.search "deep cut on my arm, bleeding won't stop"
"""

from __future__ import annotations

import re
import sqlite3
import sys

from .common import CATEGORIES, LIBRARY_DB, STOPWORDS

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set(STOPWORDS)
_CATEGORY_TERMS = {cid: terms for cid, _, terms in CATEGORIES}


def build_match_query(question: str, category: str | None = None) -> str:
    """Lowercase, keep alphanumerics, drop stopwords and 1 letter tokens, OR them.
    Returns "" when nothing searchable is left."""
    text = question.lower().replace("'", "")
    if category and category in _CATEGORY_TERMS:
        text += " " + _CATEGORY_TERMS[category]
    seen: list[str] = []
    for tok in _TOKEN.findall(text):
        if len(tok) > 1 and tok not in _STOP and tok not in seen:
            seen.append(tok)
    return " OR ".join(f'"{t}"' for t in seen[:24])


SEARCH_SQL = """
SELECT c.id, c.doc_short, c.chapter, c.page_start, c.page_end, c.text, bm25(chunks_fts) AS score
FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid
WHERE chunks_fts MATCH ?
ORDER BY score
LIMIT ?
"""


def search(conn: sqlite3.Connection, question: str, k: int = 3, category: str | None = None) -> list[dict]:
    q = build_match_query(question, category)
    if not q:
        return []
    rows = conn.execute(SEARCH_SQL, (q, k)).fetchall()
    return [
        {
            "id": r[0],
            "doc_short": r[1],
            "chapter": r[2],
            "page_start": r[3],
            "page_end": r[4],
            "text": r[5],
            "score": r[6],
        }
        for r in rows
    ]


def source_label(hit: dict) -> str:
    pages = f"p {hit['page_start']}" if hit["page_start"] == hit["page_end"] else f"pp {hit['page_start']} to {hit['page_end']}"
    return f"{hit['doc_short']}, ch {hit['chapter']}, {pages}"


if __name__ == "__main__":
    conn = sqlite3.connect(LIBRARY_DB)
    for h in search(conn, " ".join(sys.argv[1:]) or "stop bleeding", k=5):
        print(f"{h['score']:.2f}  [{source_label(h)}]  {h['text'][:140]}...")
