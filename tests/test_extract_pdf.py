"""End to end extract test on a generated PDF (skipped if reportlab is not installed)."""

import json

import pytest

reportlab = pytest.importorskip("reportlab")


def test_extract_doc_on_generated_pdf(tmp_path, monkeypatch):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    import pipeline.extract as ex

    raw, work = tmp_path / "raw", tmp_path / "work"
    raw.mkdir()
    c = canvas.Canvas(str(raw / "doc_t.pdf"), pagesize=letter)
    for i in range(1, 7):
        c.drawString(72, 740, "RUNNING HEADER LINE")
        if i == 1:
            c.drawString(72, 700, "CHAPTER 3")
        c.drawString(72, 680, f"Synthetic test body text for page {i} only.")
        c.showPage()
    c.save()

    monkeypatch.setattr(ex, "RAW", raw)
    monkeypatch.setattr(ex, "WORK", work)
    assert ex.extract_doc("doc_t") == 6
    pages = [json.loads(l) for l in (work / "doc_t.pages.jsonl").read_text().splitlines()]
    assert pages[0]["page"] == 1 and "CHAPTER 3" in pages[0]["text"]
    assert all("RUNNING HEADER LINE" not in p["text"] for p in pages)
    assert "page 6" in pages[5]["text"]
