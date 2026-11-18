"""Build build/library.sqlite from corpus/work/*.pages.jsonl.

Tables
  meta(key, value)                 build info, schema version, categories json
  docs(id, short, title, url, sha256)
  chunks(id, doc_id, doc_short, chapter, page_start, page_end, text)
  chunks_fts                       FTS5 index over chunks.text (porter + unicode61)
  stopwords(word)                  read by the iOS app so both sides tokenize the same
  field_cards(id, title, subtitle, category, reviewed, chunk_ids_json)

Also writes build/library_manifest.json (sha256 of the db) for the app readiness check.
Refuses to overwrite an existing library: it moves the old one to build/_archive/ first.

    python -m pipeline.build_library
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
from pathlib import Path

from .chunk import chunk_pages
from .common import BUILD, CARDS_YAML, CATEGORIES, LIBRARY_DB, RAW, STOPWORDS, WORK, load_sources, sha256_file
from .search import search

SCHEMA_VERSION = "1"

DDL = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE docs(id TEXT PRIMARY KEY, short TEXT NOT NULL, title TEXT NOT NULL, url TEXT, sha256 TEXT);
CREATE TABLE chunks(
  id INTEGER PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES docs(id),
  doc_short TEXT NOT NULL,
  chapter TEXT NOT NULL,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  text TEXT NOT NULL
);
CREATE VIRTUAL TABLE chunks_fts USING fts5(text, content='chunks', content_rowid='id', tokenize='porter unicode61');
CREATE TABLE stopwords(word TEXT PRIMARY KEY);
CREATE TABLE field_cards(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, subtitle TEXT NOT NULL, category TEXT NOT NULL,
  reviewed INTEGER NOT NULL, chunk_ids_json TEXT NOT NULL
);
"""


def _archive_existing(path: Path) -> None:
    if path.exists():
        arch = path.parent / "_archive"
        arch.mkdir(exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        moved = arch / f"{path.stem}_{stamp}{path.suffix}"
        shutil.move(str(path), moved)
        print(f"[arch] previous {path.name} -> {moved.relative_to(path.parent.parent)}")


def load_pages(doc_id: str, work_dir: Path = WORK) -> list[dict]:
    path = work_dir / f"{doc_id}.pages.jsonl"
    with path.open() as f:
        return [json.loads(line) for line in f]


def select_card_chunks(conn: sqlite3.Connection, card: dict) -> list[int]:
    if "pages" in card:
        p = card["pages"]
        rows = conn.execute(
            "SELECT id FROM chunks WHERE doc_id=? AND page_end>=? AND page_start<=? ORDER BY id",
            (p["doc"], p["from"], p["to"]),
        ).fetchall()
        return [r[0] for r in rows]
    hits = search(conn, card["query"], k=int(card.get("max_chunks", 3)))
    return [h["id"] for h in hits]


def build(
    docs: list[dict] | None = None,
    work_dir: Path = WORK,
    out: Path = LIBRARY_DB,
    cards: list[dict] | None = None,
) -> dict:
    import yaml

    docs = docs if docs is not None else load_sources()
    if cards is None:
        cards = yaml.safe_load(CARDS_YAML.read_text())["cards"] if CARDS_YAML.exists() else []
    raw_manifest = {}
    if (RAW / "manifest.json").exists():
        raw_manifest = json.loads((RAW / "manifest.json").read_text())

    out.parent.mkdir(parents=True, exist_ok=True)
    _archive_existing(out)
    conn = sqlite3.connect(out)
    conn.executescript(DDL)

    total = 0
    included: list[str] = []
    for d in docs:
        if not (work_dir / f"{d['id']}.pages.jsonl").exists():
            print(f"[skip] {d['id']}: no extracted pages")
            continue
        conn.execute(
            "INSERT INTO docs VALUES (?,?,?,?,?)",
            (d["id"], d["short"], d["title"], d.get("url"), raw_manifest.get(d["id"], {}).get("sha256")),
        )
        chunks = chunk_pages(load_pages(d["id"], work_dir))
        conn.executemany(
            "INSERT INTO chunks(doc_id, doc_short, chapter, page_start, page_end, text) VALUES (?,?,?,?,?,?)",
            [(d["id"], d["short"], c.chapter, c.page_start, c.page_end, c.text) for c in chunks],
        )
        total += len(chunks)
        included.append(d["id"])
        print(f"[ok] {d['id']}: {len(chunks)} chunks")

    if total == 0:
        conn.close()
        out.unlink()
        raise SystemExit("No documents extracted. Run pipeline.fetch then pipeline.extract.")

    conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
    conn.executemany("INSERT INTO stopwords VALUES (?)", [(w,) for w in STOPWORDS])

    card_report = []
    for card in cards:
        ids = select_card_chunks(conn, card)
        conn.execute(
            "INSERT INTO field_cards VALUES (?,?,?,?,?,?)",
            (card["id"], card["title"], card.get("subtitle", ""), card.get("category", ""),
             1 if card.get("reviewed") else 0, json.dumps(ids)),
        )
        card_report.append((card["id"], len(ids), bool(card.get("reviewed"))))
        if not ids:
            print(f"[WARN] card {card['id']}: no chunks matched")

    built_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    meta = {
        "schema_version": SCHEMA_VERSION,
        "built_at": built_at,
        "documents": json.dumps(included),
        "chunk_count": str(total),
        "categories": json.dumps([{"id": c, "label": l, "terms": t} for c, l, t in CATEGORIES]),
    }
    conn.executemany("INSERT INTO meta VALUES (?,?)", list(meta.items()))
    conn.commit()
    ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.execute("VACUUM")
    conn.close()
    if ok != "ok":
        raise SystemExit(f"integrity_check failed: {ok}")

    manifest = {
        "file": out.name,
        "sha256": sha256_file(out),
        "bytes": out.stat().st_size,
        "schema_version": SCHEMA_VERSION,
        "built_at": built_at,
        "chunk_count": total,
        "documents": included,
    }
    (out.parent / "library_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"[ok] {out} : {total} chunks, {out.stat().st_size/1e6:.1f} MB")
    for cid, n, rev in card_report:
        print(f"     card {cid:22s} {n} chunk(s)  {'reviewed' if rev else 'UNREVIEWED'}")
    return manifest


if __name__ == "__main__":
    build()
