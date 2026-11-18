"""Validate raw teacher output and write mlx-lm chat data (data/train.jsonl, data/valid.jsonl).

Hard checks (item dropped if any fails):
  format      starts with DO NOW or NOT IN LIBRARY, sections in order, nothing extra
  steps       DO NOW has 1..6 consecutively numbered steps, each <= 20 words
  sources     DO NOW has a SOURCES line, every [S#] exists in the user message
  refusal     NOT IN LIBRARY has no SOURCES line and <= 2 CHECK questions
  check       CHECK lines start with "- " and end with "?", at most 3
  length      reply <= 900 characters, no <think> tags
  duplicate   same normalized question seen before

Human review gate (on by default):
  items flagged medical / plant / water by the teacher, or matching risk keywords,
  are held out of training until their id is listed in training/review/approved_ids.txt.
  A review queue CSV is written so you can work through them.

    python -m training.validate_dataset training/out/aposurvive_dataset_raw_<date>_v01.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from pipeline.common import ROOT

DATA_DIR = ROOT / "data"
REVIEW_DIR = ROOT / "training" / "review"
APPROVED = REVIEW_DIR / "approved_ids.txt"

RISK_WORDS = re.compile(
    r"\b(tourniquet|bleed\w*|wound|fracture|splint|burn|shock|cpr|poison\w*|dose|mg|medicine|"
    r"antibiotic|infection|hypotherm\w*|frostbite|heat ?stroke|edib\w*|eat|mushroom|fung\w*|"
    r"berr\w*|plant|leaf|leaves|root|insect|snake|drink\w*|water|boil|iodine|chlorine)\b",
    re.IGNORECASE,
)
_STEP = re.compile(r"^(\d+)\.\s+(.+)$")
_SRC = re.compile(r"\[S(\d+)\]")


def check_reply(reply: str, n_sources: int) -> list[str]:
    errs: list[str] = []
    if "<think>" in reply or "</think>" in reply:
        errs.append("think_tag")
    if len(reply) > 900:
        errs.append("too_long")
    lines = [l.rstrip() for l in reply.strip().split("\n") if l.strip()]
    if not lines:
        return errs + ["empty"]
    head = lines[0].strip()
    try:
        check_at = lines.index("CHECK")
    except ValueError:
        check_at = len(lines)
    checks = lines[check_at + 1:]
    if len(checks) > 3:
        errs.append("too_many_checks")
    for c in checks:
        if not (c.startswith("- ") and c.endswith("?")):
            errs.append("bad_check_line")
            break

    if head == "DO NOW":
        body = lines[1:check_at]
        src_lines = [l for l in body if l.startswith("SOURCES:")]
        steps = [l for l in body if not l.startswith("SOURCES:")]
        if len(src_lines) != 1 or body[-1] != src_lines[0]:
            errs.append("sources_line")
        else:
            refs = [int(x) for x in _SRC.findall(src_lines[0])]
            if not refs:
                errs.append("no_source_refs")
            elif any(r < 1 or r > n_sources for r in refs):
                errs.append("bad_source_ref")
        if not 1 <= len(steps) <= 6:
            errs.append("step_count")
        for i, s in enumerate(steps, start=1):
            m = _STEP.match(s)
            if not m or int(m.group(1)) != i:
                errs.append("step_numbering")
                break
            if len(m.group(2).split()) > 20:
                errs.append("step_too_long")
                break
    elif head == "NOT IN LIBRARY":
        body = lines[1:check_at]
        if any(l.startswith("SOURCES:") for l in lines):
            errs.append("refusal_has_sources")
        if len(body) != 1:
            errs.append("refusal_body")
        if len(checks) > 2:
            errs.append("refusal_too_many_checks")
    else:
        errs.append("bad_header")
    return errs


def count_sources(user_msg: str) -> int:
    return len(re.findall(r"^\[S\d+\] \(", user_msg, re.MULTILINE))


def needs_review(rec: dict) -> bool:
    if set(rec.get("review_flags") or []) & {"medical", "plant", "water"}:
        return True
    reply = rec["messages"][2]["content"]
    return not reply.startswith("NOT IN LIBRARY") and bool(RISK_WORDS.search(rec["question"] + " " + reply))


def norm_q(q: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", q.lower()).strip()


def split_of(rec_id: str, valid_pct: int = 10) -> str:
    h = int(hashlib.sha1(rec_id.encode()).hexdigest(), 16) % 100
    return "valid" if h < valid_pct else "train"


def validate(raw_paths: list[Path], require_review: bool = True, out_dir: Path = DATA_DIR,
             review_dir: Path = REVIEW_DIR) -> dict:
    approved: set[str] = set()
    approved_file = review_dir / "approved_ids.txt"
    if approved_file.exists():
        approved = {l.strip() for l in approved_file.read_text().splitlines() if l.strip() and not l.startswith("#")}

    stats: Counter[str] = Counter()
    seen: set[str] = set()
    kept: dict[str, list[dict]] = {"train": [], "valid": []}
    queue: list[dict] = []
    for path in raw_paths:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            stats["total"] += 1
            reply = rec["messages"][2]["content"]
            errs = check_reply(reply, count_sources(rec["messages"][1]["content"]))
            nq = norm_q(rec["question"])
            if nq in seen:
                errs.append("duplicate")
            seen.add(nq)
            if errs:
                for e in errs:
                    stats[f"drop:{e}"] += 1
                stats["dropped"] += 1
                continue
            if require_review and needs_review(rec) and rec["id"] not in approved:
                stats["held_for_review"] += 1
                queue.append(rec)
                continue
            stats["refusal" if reply.startswith("NOT IN LIBRARY") else "answer"] += 1
            kept[split_of(rec["id"])].append({"messages": rec["messages"]})

    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in kept.items():
        with (out_dir / f"{split}.jsonl").open("w") as f:  # derived data, regenerated each run
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    review_dir.mkdir(parents=True, exist_ok=True)
    with (review_dir / "review_queue.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "flags", "question", "reply", "sources_shown"])
        for r in queue:
            w.writerow([r["id"], "|".join(r.get("review_flags") or []), r["question"],
                        r["messages"][2]["content"], r["messages"][1]["content"]])

    kept_n = stats["answer"] + stats["refusal"]
    stats["kept"] = kept_n
    stats["train"] = len(kept["train"])
    stats["valid"] = len(kept["valid"])
    ratio = stats["refusal"] / kept_n if kept_n else 0.0
    report = dict(stats) | {"refusal_ratio": round(ratio, 3)}
    print(json.dumps(report, indent=2))
    if kept_n and not 0.10 <= ratio <= 0.30:
        print(f"[WARN] refusal ratio {ratio:.0%} is outside the 10% to 30% target", file=sys.stderr)
    if queue:
        print(f"[info] {len(queue)} items wait in {review_dir / 'review_queue.csv'}. "
              f"Add approved ids to {approved_file} and rerun.")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw", nargs="+", type=Path)
    ap.add_argument("--no-review-gate", action="store_true", help="train on unreviewed risky items (not recommended)")
    a = ap.parse_args()
    validate(a.raw, require_review=not a.no_review_gate)
