"""Generate grounded training examples with DeepSeek as the teacher.

Per seed chunk:
  1. teacher writes realistic questions (some answerable by the seed, some not)
  2. the SAME BM25 retrieval the phone uses picks 3 sources for each question
     (answerable questions always get the seed among them, at a random slot)
  3. teacher writes the ideal reply in the runtime format, given exactly those sources

Output is a new versioned file, never an overwrite:
  training/out/aposurvive_dataset_raw_<YYYYMMDD>_vNN.jsonl

    export DEEPSEEK_API_KEY=...         # never commit this
    python -m training.gen_dataset --seeds 40            # dry run: prints plan and cost driver
    python -m training.gen_dataset --seeds 40 --yes      # spends API credit
    python -m training.gen_dataset --resume training/out/<file>.jsonl --yes
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Callable

from pipeline.common import CATEGORY_IDS, LIBRARY_DB, ROOT
from pipeline.search import search, source_label
from training.prompt_format import PROMPTS, RUNTIME_SYSTEM, format_user_message

OUT_DIR = ROOT / "training" / "out"
DEFAULT_MODEL = "deepseek-v4-pro"  # deepseek-chat / deepseek-reasoner aliases retired 2026-07-24
BASE_URL = "https://api.deepseek.com"

Complete = Callable[[str], str]


def next_versioned_path(out_dir: Path, stem: str, ext: str = ".jsonl", today: str | None = None) -> Path:
    today = today or dt.date.today().strftime("%Y%m%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    v = 1
    while (p := out_dir / f"{stem}_{today}_v{v:02d}{ext}").exists():
        v += 1
    return p


def deepseek_client(model: str) -> Complete:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("Set DEEPSEEK_API_KEY in your environment (never in the repo).")
    from openai import OpenAI

    client = OpenAI(api_key=key, base_url=BASE_URL)

    def complete(prompt: str) -> str:
        for attempt in range(4):
            try:
                r = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.7,
                )
                return r.choices[0].message.content or ""
            except Exception as e:
                wait = 2 ** attempt * 3
                print(f"  [retry {attempt + 1}] {type(e).__name__}: {e}. waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
        raise RuntimeError("teacher call failed 4 times")

    return complete


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def is_good_seed(text: str) -> bool:
    words = text.split()
    if len(words) < 80:
        return False
    digits = sum(ch.isdigit() for ch in text)
    return digits / max(len(text), 1) < 0.08  # skips tables of contents and indexes


def sample_seeds(conn: sqlite3.Connection, n: int, rng: random.Random) -> list[dict]:
    rows = conn.execute("SELECT id, doc_id, doc_short, chapter, page_start, page_end, text FROM chunks").fetchall()
    by_group: dict[tuple, list] = {}
    for r in rows:
        if is_good_seed(r[6]):
            by_group.setdefault((r[1], r[3]), []).append(r)
    groups = list(by_group.values())
    for g in groups:
        rng.shuffle(g)
    rng.shuffle(groups)
    seeds, i = [], 0
    while len(seeds) < n and any(groups):  # round robin over doc/chapter groups
        g = groups[i % len(groups)]
        if g:
            r = g.pop()
            seeds.append(dict(zip(["id", "doc_id", "doc_short", "chapter", "page_start", "page_end", "text"], r)))
        i += 1
        if i > 10 * (n + len(groups)) and not any(groups):
            break
    return seeds


def retrieve_for(conn, question: str, category: str | None, seed: dict, answerable: bool, rng: random.Random, k: int = 3) -> list[dict]:
    hits = search(conn, question, k=k + 1, category=category)
    hits = [h for h in hits if h["id"] != seed["id"]][: k if not answerable else k - 1]
    if answerable:
        hits.insert(rng.randrange(len(hits) + 1), {**seed, "score": 0.0})
    return hits[:k]


def generate(
    complete: Complete,
    conn: sqlite3.Connection,
    seeds: list[dict],
    out_path: Path,
    model: str,
    n_answerable: int = 3,
    n_unanswerable: int = 1,
    rng: random.Random | None = None,
    done_seed_ids: set[int] | None = None,
) -> int:
    rng = rng or random.Random(7)
    done_seed_ids = done_seed_ids or set()
    q_tmpl = (PROMPTS / "teacher_questions.md").read_text()
    a_tmpl = (PROMPTS / "teacher_answer.md").read_text()
    written = 0
    with out_path.open("a") as out:
        for si, seed in enumerate(seeds, start=1):
            if seed["id"] in done_seed_ids:
                continue
            label = source_label(seed)
            try:
                qs = parse_json(complete(q_tmpl.format(
                    n_answerable=n_answerable, n_unanswerable=n_unanswerable,
                    categories=", ".join(CATEGORY_IDS), source_label=label, seed_text=seed["text"],
                )))["questions"]
            except Exception as e:
                print(f"[seed {seed['id']}] question step failed: {e}", file=sys.stderr)
                continue
            for qi, q in enumerate(qs):
                question = str(q.get("q", "")).strip()
                category = q.get("category") if q.get("category") in CATEGORY_IDS else None
                answerable = bool(q.get("answerable"))
                if not question:
                    continue
                hits = retrieve_for(conn, question, category, seed, answerable, rng)
                user_msg = format_user_message(question, category, hits)
                try:
                    a = parse_json(complete(a_tmpl.format(system_rules=RUNTIME_SYSTEM, user_message=user_msg)))
                except Exception as e:
                    print(f"[seed {seed['id']} q{qi}] answer step failed: {e}", file=sys.stderr)
                    continue
                rec = {
                    "id": f"s{seed['id']}_q{qi}",
                    "seed_chunk_id": seed["id"],
                    "question": question,
                    "category": category,
                    "q_answerable": answerable,
                    "hit_chunk_ids": [h["id"] for h in hits],
                    "refusal": bool(a.get("refusal")),
                    "used_sources": a.get("used_sources", []),
                    "review_flags": a.get("review_flags", []),
                    "teacher_model": model,
                    "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "messages": [
                        {"role": "system", "content": RUNTIME_SYSTEM},
                        {"role": "user", "content": user_msg},
                        {"role": "assistant", "content": str(a.get("answer", "")).strip()},
                    ],
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                written += 1
            print(f"[{si}/{len(seeds)}] seed {seed['id']} ({label}) -> {written} examples so far")
    return written


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--answerable", type=int, default=3)
    ap.add_argument("--unanswerable", type=int, default=1)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--library", type=Path, default=LIBRARY_DB)
    ap.add_argument("--resume", type=Path, help="append to an existing raw file, skipping finished seeds")
    ap.add_argument("--rng-seed", type=int, default=7)
    ap.add_argument("--yes", action="store_true", help="actually call the API (spends credit)")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.library)
    rng = random.Random(args.rng_seed)
    seeds = sample_seeds(conn, args.seeds, rng)
    calls = len(seeds) * (1 + args.answerable + args.unanswerable)
    print(f"Plan: {len(seeds)} seeds, up to {len(seeds) * (args.answerable + args.unanswerable)} examples, "
          f"~{calls} API calls to {args.model} at {BASE_URL}")
    if not args.yes:
        print("Dry run. Add --yes to call the API.")
        return

    done: set[int] = set()
    if args.resume:
        out_path = args.resume
        with out_path.open() as f:
            done = {json.loads(l)["seed_chunk_id"] for l in f if l.strip()}
        print(f"Resuming {out_path.name}: {len(done)} seeds already done")
    else:
        out_path = next_versioned_path(OUT_DIR, "aposurvive_dataset_raw")
    n = generate(deepseek_client(args.model), conn, seeds, out_path, args.model,
                 args.answerable, args.unanswerable, rng, done)
    print(f"\nWrote {n} examples -> {out_path}")


if __name__ == "__main__":
    main()
