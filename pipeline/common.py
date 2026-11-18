"""Shared paths, categories and stopwords. The iOS app reads categories and stopwords
from the built library, so this file is the single source of truth for both sides."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
RAW = CORPUS / "raw"
WORK = CORPUS / "work"
BUILD = ROOT / "build"
SOURCES_YAML = CORPUS / "sources.yaml"
CARDS_YAML = CORPUS / "cards.yaml"
LIBRARY_DB = BUILD / "library.sqlite"

# id, label shown in the app, extra retrieval terms appended to the user query
CATEGORIES: list[tuple[str, str, str]] = [
    ("injury", "Injury", "bleeding wound first aid"),
    ("water", "Water", "water purify procurement"),
    ("fire", "Fire", "fire tinder kindling"),
    ("shelter", "Shelter", "shelter site"),
    ("navigate", "Navigate", "navigation direction compass"),
    ("food", "Food", "food edible plants animals"),
    ("signal", "Signal", "signal rescue"),
    ("cold_heat", "Cold / heat", "cold weather hot climate exposure"),
]
CATEGORY_IDS = [c[0] for c in CATEGORIES]

STOPWORDS = sorted(
    set(
        """a an and are as at be but by can could do does for from had has have how i if in
        into is it its me my no not of on or our so that the their then there these this to
        up was we were what when where which who why will with you your im ive dont cant
        should would please help need now just get got""".split()
    )
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_sources() -> list[dict]:
    import yaml

    with SOURCES_YAML.open() as f:
        return yaml.safe_load(f)["documents"]
