"""The exact user message the phone sends. LibraryStore.swift / PromptBuilder.swift mirror
`format_user_message`, so training and inference see identical text."""

from __future__ import annotations

from pathlib import Path

from pipeline.common import CATEGORIES
from pipeline.search import source_label

PROMPTS = Path(__file__).resolve().parent / "prompts"
RUNTIME_SYSTEM = (PROMPTS / "runtime_system.txt").read_text().strip()
_LABELS = {cid: label for cid, label, _ in CATEGORIES}


def format_user_message(question: str, category: str | None, hits: list[dict]) -> str:
    lines = []
    if category:
        lines.append(f"SITUATION: {_LABELS.get(category, category)}")
    lines.append(f"QUESTION: {question.strip()}")
    lines.append("")
    lines.append("SOURCES:")
    if not hits:
        lines.append("(none found)")
    for i, h in enumerate(hits, start=1):
        lines.append(f"[S{i}] ({source_label(h)})")
        lines.append(h["text"].strip())
        lines.append("")
    return "\n".join(lines).rstrip()
