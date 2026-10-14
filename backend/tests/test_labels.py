"""The labeled eval sets (eval/*.jsonl) must say only what a perfect reading of the DAY0 farm can say:
known senders, buyers, bed labels and lines, days in range — and a perfect reading must score 100%."""

import json
from pathlib import Path

import pytest

from app import farm
from app.notes import (
    HarvestReading,
    LossReading,
    NoteReading,
    OrderReading,
    SignalReading,
    SowingReading,
    sanitize,
    score,
)
from app.store import JsonStore

EVAL = Path(__file__).resolve().parents[2] / "eval"
LABELS = [json.loads(line) for f in ("notes_labeled.jsonl", "notes_holdout.jsonl") if (EVAL / f).exists()
          for line in (EVAL / f).read_text().splitlines() if line.strip()]


def reading_from_label(e: dict) -> NoteReading:
    """The reading a perfect model would return for a label."""
    k = e["kind"]
    if k == "orders":
        return NoteReading(kind=k, summary_en="x", orders=[OrderReading(**o) for o in e["orders"]])
    if k == "harvest":
        return NoteReading(kind=k, summary_en="x", harvest=HarvestReading(**e["harvest"]))
    if k == "sowing":
        s = e["sowing"]
        return NoteReading(kind=k, summary_en="x", sowing=SowingReading(**s, reason="r" if s["postponed"] else ""))
    if k == "loss":
        return NoteReading(kind=k, summary_en="x", loss=LossReading(**e["loss"], cause="c"))
    if k == "signal":
        return NoteReading(kind=k, summary_en="x", signals=[SignalReading(**s, cause="c") for s in e["signals"]])
    return NoteReading(kind="none", summary_en="x")


@pytest.mark.parametrize("row", LABELS, ids=[r["id"] for r in LABELS])
def test_every_label_survives_the_sanitizer_and_scores_perfect(row):
    inp = farm.note_inputs(JsonStore())
    assert row["received_on"] == inp["today"].isoformat()
    assert row["sender"] in {"farmer", "operator"} | {b["id"] for b in JsonStore().list("buyers")}
    got, dropped = sanitize(reading_from_label(row["expected"]), inp["today"], JsonStore().list("buyers"),
                            inp["beds"], inp["lines"], inp["max_seedlings"])
    s = score(row["expected"], got)
    assert not dropped and s["kind_ok"] and all(s["fields"].values()) and s["extra"] == 0


def test_label_ids_are_unique():
    assert len({r["id"] for r in LABELS}) == len(LABELS)
