"""Extract per page text from corpus/raw/<id>.pdf into corpus/work/<id>.pages.jsonl.

Page numbers are 1 based PDF page indexes (not the printed folio). The app labels
them "p" and the source sheet shows the verbatim text, so a reader can always check.

    python -m pipeline.extract
"""

from __future__ import annotations

import json
import re
from collections import Counter

from .common import RAW, WORK, load_sources

_LINEBREAK_HYPHEN = re.compile(r"(\w)-\n(\w)")
_MULTI_SPACE = re.compile(r"[ \t ]+")
_DOT_LEADER = re.compile(r"\.{4,}")


def clean_page(text: str) -> str:
    text = text.replace("\r", "\n")
    text = _LINEBREAK_HYPHEN.sub(r"\1\2", text)  # tour-\nniquet -> tourniquet
    text = _DOT_LEADER.sub(" ", text)
    lines = [_MULTI_SPACE.sub(" ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def strip_running_lines(pages: list[str], threshold: float = 0.3) -> list[str]:
    """Drop header/footer lines that repeat on more than `threshold` of pages."""
    if len(pages) < 5:
        return pages
    counts: Counter[str] = Counter()
    for p in pages:
        counts.update(set(p.split("\n")))
    limit = max(3, int(len(pages) * threshold))
    running = {ln for ln, n in counts.items() if n >= limit and len(ln) < 80}
    return ["\n".join(ln for ln in p.split("\n") if ln not in running) for p in pages]


def extract_doc(doc_id: str) -> int:
    from pypdf import PdfReader

    src = RAW / f"{doc_id}.pdf"
    reader = PdfReader(str(src))
    raw_pages = [clean_page(page.extract_text() or "") for page in reader.pages]
    pages = strip_running_lines(raw_pages)
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"{doc_id}.pages.jsonl"
    with out.open("w") as f:
        for i, text in enumerate(pages, start=1):
            f.write(json.dumps({"doc": doc_id, "page": i, "text": text}) + "\n")
    empty = sum(1 for p in pages if len(p) < 20)
    print(f"[ok] {doc_id}: {len(pages)} pages, {empty} near empty -> {out.name}")
    if empty > len(pages) * 0.5:
        print(f"[WARN] {doc_id}: over half the pages have no text. Scanned PDF? OCR needed.")
    return len(pages)


if __name__ == "__main__":
    for d in load_sources():
        if (RAW / f"{d['id']}.pdf").exists():
            extract_doc(d["id"])
        else:
            print(f"[skip] {d['id']}: no PDF in corpus/raw (run pipeline.fetch)")
