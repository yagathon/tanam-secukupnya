import json
from datetime import date
from pathlib import Path

import pytest

from app import notes
from app.notes import NoteReading, sanitize, score
from app.store import JsonStore

LABELS = Path(__file__).resolve().parents[2] / "eval" / "notes_labeled.jsonl"


@pytest.fixture(scope="module")
def state():
    s = JsonStore()
    return {"today": "2026-10-12", **{c: s.list(c) for c in ("crops", "farmers", "partners", "households")}}


@pytest.fixture(scope="module")
def labeled():
    return [json.loads(line) for line in LABELS.read_text().splitlines() if line.strip()]


def is_monday(s):
    return date.fromisoformat(s).weekday() == 0


def test_label_set_is_valid(labeled, state):
    """Every label must be something a perfect model could output, or the benchmark lies."""
    assert 30 <= len(labeled) <= 50
    ids = [r["id"] for r in labeled]
    assert len(ids) == len(set(ids))
    partners = {p["id"] for p in state["partners"]}
    farmers = {f["id"]: set(f["crops"]) for f in state["farmers"]}
    crops = {c["id"] for c in state["crops"]}
    for r in labeled:
        assert r["sender"] in partners | set(farmers) | {"operator"}, r["id"]
        assert is_monday(r["received_on"]), r["id"]
        e = r["expected"]
        assert e["kind"] in notes.KINDS, r["id"]
        if e["kind"] == "signals":
            assert e["signals"], r["id"]
            for s in e["signals"]:
                assert s["scope"] in {"all", "channel:B2B", "channel:B2C"} | {f"partner:{p}" for p in partners}, r["id"]
                assert s["crop"] is None or s["crop"] in crops, r["id"]
                assert -100 <= s["effect_pct"] <= 300, r["id"]
                assert is_monday(s["week_from"]), r["id"]
                assert s["week_to"] is None or (is_monday(s["week_to"]) and s["week_to"] >= s["week_from"]), r["id"]
                assert s["cause_category"] in notes.DEMAND_CAUSES, r["id"]
        elif e["kind"] == "harvest_issue":
            h = e["harvest_issue"]
            assert h["crop"] in farmers[h["farmer_id"]], r["id"]
            assert 0 <= h["loss_pct"] <= 100 and h["delay_days"] >= 0, r["id"]
            assert h["harvest_week"] is None or is_monday(h["harvest_week"]), r["id"]
            assert h["cause_category"] in notes.HARVEST_CAUSES, r["id"]


def test_label_set_covers_the_cases(labeled):
    kinds = [r["expected"]["kind"] for r in labeled]
    assert kinds.count("signals") >= 20 and kinds.count("harvest_issue") >= 10 and kinds.count("none") >= 8
    assert any(len(r["expected"].get("signals", [])) > 1 for r in labeled)


def test_a_perfect_reading_scores_perfectly(labeled, state):
    for r in labeled:
        e = json.loads(json.dumps(r["expected"]))  # labels score cause_category only; free text is not scored
        for x in e.get("signals", []) + ([e["harvest_issue"]] if e.get("harvest_issue") else []):
            x["cause"] = "x"
        reading = NoteReading(**e, summary_en="x")
        got, dropped = sanitize(reading, state)
        assert not dropped, r["id"]
        res = score(r["expected"], got)
        assert res["kind_ok"] and all(res["fields"].values()) and res["extra"] == 0, (r["id"], res)


def test_sanitize_drops_what_the_model_could_not_know(state):
    r = NoteReading(kind="signals", summary_en="x", signals=[
        {"scope": "partner:resto_z", "crop": None, "effect_pct": 10, "week_from": "2026-10-19",
         "week_to": None, "cause": "x", "cause_category": "event"},
        {"scope": "all", "crop": "kale", "effect_pct": 10, "week_from": "2026-10-19",
         "week_to": None, "cause": "x", "cause_category": "event"},
        {"scope": "all", "crop": None, "effect_pct": 900, "week_from": "2026-10-21",
         "week_to": "2026-10-14", "cause": "x", "cause_category": "event"},
    ])
    got, dropped = sanitize(r, state)
    assert len(dropped) == 2
    [s] = got["signals"]
    assert s["effect_pct"] == 300 and s["week_from"] == "2026-10-19" and s["week_to"] == "2026-10-19"


def test_sanitize_rejects_a_farmer_reporting_a_crop_they_do_not_grow(state):
    r = NoteReading(kind="harvest_issue", summary_en="x", harvest_issue={
        "farmer_id": "farmer_a", "crop": "sawi_putih", "loss_pct": 30, "harvest_week": None,
        "cause": "x", "cause_category": "pest"})
    got, dropped = sanitize(r, state)
    assert got["kind"] == "none" and dropped


def test_bucket():
    assert [notes.bucket(p) for p in (-100, -50, -20, -5, 0, 10, 30, 100)] == \
        ["stop", "-large", "-medium", "-small", "zero", "+small", "+medium", "+large"]


def test_week_table_starts_on_this_monday():
    t = notes.week_table(date(2026, 10, 14), 3)
    assert [w["monday"] for w in t] == ["2026-10-12", "2026-10-19", "2026-10-26"]
