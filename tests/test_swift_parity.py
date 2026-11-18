"""Guards that the Swift app and the Python training pipeline build identical prompts.
The model is trained on Python formatted prompts and served Swift formatted ones,
so any drift silently degrades the fine tune. (Swift is not compiled here.)"""

import re
from pathlib import Path

from pipeline.common import CATEGORIES
from pipeline.search import SEARCH_SQL, source_label
from training.prompt_format import format_user_message

IOS = Path(__file__).resolve().parent.parent / "ios" / "AposurviveOffline"


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def test_search_sql_matches():
    swift = (IOS / "Services" / "LibraryStore.swift").read_text()
    m = re.search(r'let sql = """(.*?)"""', swift, re.DOTALL)
    assert m, "search SQL not found in LibraryStore.swift"
    assert _norm(m.group(1)) == _norm(SEARCH_SQL)


def test_label_format_matches():
    swift = (IOS / "Models" / "Models.swift").read_text()
    assert 'pageStart == pageEnd ? "p \\(pageStart)" : "pp \\(pageStart) to \\(pageEnd)"' in swift
    assert '"\\(docShort), ch \\(chapter), \\(pages)"' in swift
    hit = {"doc_short": "ATP 3-50.21", "chapter": "4", "page_start": 50, "page_end": 51, "text": "x"}
    assert source_label(hit) == "ATP 3-50.21, ch 4, pp 50 to 51"


def test_user_message_markers_match():
    swift = (IOS / "Services" / "PromptBuilder.swift").read_text()
    for marker in ['"SITUATION: \\(categoryLabel)"', '"QUESTION: \\(', '"SOURCES:"', '"(none found)"', '"[S\\(i + 1)] (\\(s.label))"']:
        assert marker in swift, marker
    msg = format_user_message("q", "injury", [])
    assert msg == "SITUATION: Injury\nQUESTION: q\n\nSOURCES:\n(none found)"


def test_category_symbols_cover_all_categories():
    swift = (IOS / "Models" / "Models.swift").read_text()
    for cid, _, _ in CATEGORIES:
        assert f'case "{cid}"' in swift, cid
