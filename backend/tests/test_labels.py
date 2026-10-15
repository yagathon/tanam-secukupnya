"""The labeled eval sets (eval/*.jsonl) must say only what a perfect reading of their farm (DAY0, or
eval/sandbox_setup.json for notes_sandbox.jsonl) can say:
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
from app.sandbox import SandboxStore, SetupIn
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


SANDBOX_LABELS = [json.loads(line) for line in (EVAL / "notes_sandbox.jsonl").read_text().splitlines() if line.strip()]


def sandbox_ws() -> SandboxStore:
    """The fixed sandbox farm the sandbox labels refer to (Bed 1..3, buyers b1..b4)."""
    setup = SetupIn.model_validate(json.loads((EVAL / "sandbox_setup.json").read_text())).model_dump(mode="json")
    return SandboxStore(JsonStore().for_user("eval"), setup)


@pytest.mark.parametrize("row,ws", [(r, JsonStore) for r in LABELS] + [(r, sandbox_ws) for r in SANDBOX_LABELS],
                         ids=[r["id"] for r in LABELS + SANDBOX_LABELS])
def test_every_label_survives_the_sanitizer_and_scores_perfect(row, ws):
    ws = ws()
    inp = farm.note_inputs(ws)
    assert row["received_on"] == inp["today"].isoformat()
    assert row["sender"] in {"farmer", "operator"} | {b["id"] for b in ws.list("buyers")}
    got, dropped = sanitize(reading_from_label(row["expected"]), inp["today"], ws.list("buyers"),
                            inp["beds"], inp["lines"], inp["max_seedlings"])
    s = score(row["expected"], got)
    assert not dropped and s["kind_ok"] and all(s["fields"].values()) and s["extra"] == 0


def test_label_ids_are_unique():
    rows = LABELS + SANDBOX_LABELS
    assert len({r["id"] for r in rows}) == len(rows)


def test_sandbox_set_covers_every_kind():
    kinds = [r["expected"]["kind"] for r in SANDBOX_LABELS]
    assert len(SANDBOX_LABELS) == 15
    assert {k: kinds.count(k) for k in set(kinds)} == {"orders": 6, "harvest": 4, "loss": 2, "sowing": 2, "signal": 1}
