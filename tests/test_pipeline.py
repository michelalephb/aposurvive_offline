import json
import sqlite3

from pipeline.build_library import build
from pipeline.chunk import chunk_pages, detect_section
from pipeline.extract import clean_page, strip_running_lines
from pipeline.search import build_match_query, search, source_label

# Synthetic text written for tests only. It is NOT survival guidance and never ships.
LOREM = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima."


def _pages(doc="doc_a", n=6, words_per_page=150):
    pages = []
    for i in range(1, n + 1):
        body = " ".join(LOREM for _ in range(words_per_page // 12))
        head = f"CHAPTER {1 if i <= 3 else 2}\n" if i in (1, 4) else ""
        pages.append({"doc": doc, "page": i, "text": head + body})
    return pages


def test_clean_page_joins_linebreak_hyphen_and_dot_leaders():
    assert clean_page("tour-\nniquet") == "tourniquet"
    assert "....." not in clean_page("Contents ........ 12")


def test_strip_running_lines_removes_repeated_headers():
    pages = [f"ATP 3-50.21\nbody text {i}" for i in range(10)]
    out = strip_running_lines(pages)
    assert all("ATP 3-50.21" not in p for p in out)
    assert out[3] == "body text 3"


def test_detect_section():
    assert detect_section("Chapter 7\nMovement", "?") == "7"
    assert detect_section("Appendix B\nEdible plants", "7") == "App B"
    assert detect_section("no heading here", "7") == "7"


def test_chunks_cover_all_pages_with_overlap_and_chapters():
    chunks = chunk_pages(_pages(), target_words=200, overlap_words=30)
    assert chunks[0].page_start == 1 and chunks[-1].page_end == 6
    assert chunks[0].chapter == "1"
    assert chunks[-1].chapter == "2"
    for a, b in zip(chunks, chunks[1:]):
        assert b.page_start <= a.page_end  # overlap keeps continuity
    # most chunks end on a sentence boundary
    assert sum(c.text.endswith(".") for c in chunks) >= len(chunks) - 1


def test_match_query_drops_stopwords_and_adds_category_terms():
    q = build_match_query("How do I stop the bleeding? It won't stop!", category="injury")
    assert '"bleeding"' in q and '"stop"' in q and '"wont"' in q
    assert '"how"' not in q and '"the"' not in q
    assert '"wound"' in q  # category expansion
    assert build_match_query("the a an") == ""


def test_build_library_and_search(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    pages = _pages()
    pages[4]["text"] += " zulu tourniquet procedure zulu."
    with (work / "doc_a.pages.jsonl").open("w") as f:
        for p in pages:
            f.write(json.dumps(p) + "\n")
    docs = [{"id": "doc_a", "short": "DOC A", "title": "Test doc", "url": None}]
    cards = [{"id": "tq", "title": "Tq", "query": "tourniquet", "max_chunks": 2, "reviewed": False}]
    out = tmp_path / "build" / "library.sqlite"
    manifest = build(docs=docs, work_dir=work, out=out, cards=cards)
    assert manifest["chunk_count"] > 0
    assert (out.parent / "library_manifest.json").exists()

    conn = sqlite3.connect(out)
    hits = search(conn, "tourniquet")
    assert hits and "tourniquet" in hits[0]["text"]
    assert hits[0]["page_end"] >= 5
    assert source_label(hits[0]).startswith("DOC A, ch 2")
    card = conn.execute("SELECT reviewed, chunk_ids_json FROM field_cards WHERE id='tq'").fetchone()
    assert card[0] == 0 and json.loads(card[1])[0] == hits[0]["id"]
    assert conn.execute("SELECT count(*) FROM stopwords").fetchone()[0] > 20

    # rebuilding archives the previous db instead of overwriting it
    build(docs=docs, work_dir=work, out=out, cards=cards)
    assert len(list((out.parent / "_archive").glob("library_*.sqlite"))) == 1
