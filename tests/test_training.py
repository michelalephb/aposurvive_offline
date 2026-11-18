import json
import random
import sqlite3

from pipeline.build_library import build
from training.gen_dataset import generate, next_versioned_path, parse_json, retrieve_for, sample_seeds
from training.prompt_format import RUNTIME_SYSTEM, format_user_message
from training.validate_dataset import check_reply, count_sources, validate

GOOD = "DO NOW\n1. Do the first thing now.\n2. Then do the second thing.\nSOURCES: [S1] [S2]\nCHECK\n- Is it still happening?"
REFUSE = "NOT IN LIBRARY\nNo source covers this; open the Signal field card.\nCHECK\n- Are you near a road?"


def test_check_reply_accepts_good_formats():
    assert check_reply(GOOD, 3) == []
    assert check_reply(REFUSE, 3) == []


def test_check_reply_catches_errors():
    assert "bad_source_ref" in check_reply(GOOD.replace("[S2]", "[S4]"), 3)
    assert "step_numbering" in check_reply(GOOD.replace("2. Then", "3. Then"), 3)
    assert "bad_header" in check_reply("Sure! Here is help.", 3)
    assert "refusal_has_sources" in check_reply(REFUSE + "\nSOURCES: [S1]", 3)
    assert "bad_check_line" in check_reply(GOOD.replace("- Is it still happening?", "Is it"), 3)
    assert "think_tag" in check_reply("<think>x</think>\n" + GOOD, 3)
    long_step = "DO NOW\n1. " + "word " * 25 + "\nSOURCES: [S1]\nCHECK"
    assert "step_too_long" in check_reply(long_step, 1)


def test_versioned_path_never_reuses(tmp_path):
    a = next_versioned_path(tmp_path, "x", today="20261117")
    a.write_text("")
    b = next_versioned_path(tmp_path, "x", today="20261117")
    assert a.name == "x_20261117_v01.jsonl" and b.name == "x_20261117_v02.jsonl"


def test_parse_json_tolerates_wrapping_text():
    assert parse_json('ok here: {"a": 1} thanks') == {"a": 1}


def _library(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike."
    with (work / "d.pages.jsonl").open("w") as f:
        for i in range(1, 9):
            topic = "zulu yankee" if i < 5 else "xray whiskey"
            f.write(json.dumps({"doc": "d", "page": i, "text": f"CHAPTER {1 + i // 5}\n" + f"{topic} {words} " * 14}) + "\n")
    out = tmp_path / "library.sqlite"
    build(docs=[{"id": "d", "short": "DOC D", "title": "t", "url": None}], work_dir=work, out=out, cards=[])
    return sqlite3.connect(out)


def test_retrieval_includes_seed_only_when_answerable(tmp_path):
    conn = _library(tmp_path)
    rng = random.Random(1)
    seeds = sample_seeds(conn, 3, rng)
    assert seeds
    s = seeds[0]
    hits = retrieve_for(conn, "xray whiskey", None, s, True, rng)
    assert s["id"] in [h["id"] for h in hits] and len(hits) <= 3
    hits = retrieve_for(conn, "xray whiskey", None, s, False, rng)
    assert s["id"] not in [h["id"] for h in hits]


def test_generate_and_validate_end_to_end_with_fake_teacher(tmp_path):
    conn = _library(tmp_path)
    rng = random.Random(3)
    seeds = sample_seeds(conn, 2, rng)

    def fake_teacher(prompt: str) -> str:
        if "Return JSON only:\n{\"questions\"" in prompt:
            return json.dumps({"questions": [
                {"q": "zulu yankee what now", "category": "signal", "answerable": True},
                {"q": "xray whiskey help", "category": "fire", "answerable": False},
            ]})
        if "xray" in prompt.split("USER MESSAGE:")[1]:
            return json.dumps({"answer": REFUSE, "refusal": True, "used_sources": [], "review_flags": []})
        return json.dumps({"answer": GOOD, "refusal": False, "used_sources": [1, 2], "review_flags": []})

    raw = tmp_path / "raw.jsonl"
    n = generate(fake_teacher, conn, seeds, raw, "fake", 1, 1, rng)
    assert n == 4
    rec = json.loads(raw.read_text().splitlines()[0])
    assert rec["messages"][0]["content"] == RUNTIME_SYSTEM
    assert count_sources(rec["messages"][1]["content"]) >= 2

    report = validate([raw], out_dir=tmp_path / "data", review_dir=tmp_path / "review")
    assert report["kept"] == 2  # two duplicates dropped (same question text per seed)
    assert report["drop:duplicate"] == 2
    lines = (tmp_path / "data" / "train.jsonl").read_text().splitlines() + (tmp_path / "data" / "valid.jsonl").read_text().splitlines()
    assert len(lines) == 2 and "messages" in json.loads(lines[0])


def test_review_gate_holds_risky_items(tmp_path):
    rec = {
        "id": "s1_q0", "question": "how do I use a tourniquet", "review_flags": ["medical"],
        "messages": [
            {"role": "system", "content": RUNTIME_SYSTEM},
            {"role": "user", "content": format_user_message("q", "injury", [
                {"doc_short": "D", "chapter": "1", "page_start": 1, "page_end": 1, "text": "t"},
                {"doc_short": "D", "chapter": "1", "page_start": 2, "page_end": 2, "text": "t"}])},
            {"role": "assistant", "content": GOOD},
        ],
    }
    raw = tmp_path / "raw.jsonl"
    raw.write_text(json.dumps(rec) + "\n")
    review = tmp_path / "review"
    r1 = validate([raw], out_dir=tmp_path / "data", review_dir=review)
    assert r1["held_for_review"] == 1 and r1["kept"] == 0
    (review / "approved_ids.txt").write_text("s1_q0\n")
    r2 = validate([raw], out_dir=tmp_path / "data", review_dir=review)
    assert r2["kept"] == 1
