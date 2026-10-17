"""Impact: the sandbox as logged vs. the same days under the old habit (1,000 seedlings every Thursday).

The habit run replays the log with three changes: its own sowing replaces every logged one, each day's
harvested kg (logged or assumed) is taken oldest bed first from its beds, and a logged loss hits its bed
closest in age. Orders and the reference curve are the farm's own (the habit grows on the final learned
curve), so the two runs differ only in what was sown.

Waste is decided per bed: the morning a bed's average plant is past the heaviest any buyer takes (stretch, else max; or the bed is past
max_bed_day), it closes. Whatever it still holds goes to the middleman cheap (food waste) and the bed is
free for a new sowing. A bed cut empty before that wastes nothing; an open bed is still growing.
"""

from __future__ import annotations

from datetime import date

from app.growth import Crop
from app.production import Batch, apply_loss, avg_g, bed_day, plants0, take_oldest
from app.state import FarmState, apply, current_crop, initial

HABIT_SEEDLINGS = 1000
HABIT_WEEKDAY = 3                    # Thursday: the founder's sowing day before Tanam


def _close(c: Crop, st: FarmState, closed: dict[str, date]) -> None:
    for b in st.batches.values():
        if b.id not in closed and bed_day(c, b, st.today) >= 0 and (
                bed_day(c, b, st.today) > c.max_bed_day or avg_g(c, b, st.today) > c.line(b.line).top_g):
            closed[b.id] = st.today


def _bed(c: Crop, b: Batch, closed: dict[str, date], group: str) -> dict:
    left = max(0.0, plants0(c, b) - b.harvested_plants - b.lost_plants)
    shut = closed.get(b.id)
    return {"id": b.id, "label": b.label, "line": b.line, "sown_on": b.sown_on.isoformat(), "group": group,
            "seedlings": b.seedlings, "harvested": round(b.harvested_plants), "lost": round(b.lost_plants),
            "waste": round(left) if shut else 0, "growing": 0 if shut else round(left),
            "closed_on": shut.isoformat() if shut else None}


def _row(beds: list[dict], delivered: dict[str, float]) -> dict:
    harvested, waste = sum(b["harvested"] for b in beds), sum(b["waste"] for b in beds)
    return {"beds": len(beds), "seedlings": sum(b["seedlings"] for b in beds), "harvested_plants": harvested,
            "lost_plants": sum(b["lost"] for b in beds), "waste_plants": waste,
            "in_field_plants": sum(b["growing"] for b in beds),
            "waste_pct": round(100 * waste / (harvested + waste), 1) if harvested + waste > 0 else 0.0,
            "delivered_kg": round(sum(delivered.get(b["id"], 0.0) for b in beds), 2)}


def build(ref: dict, meta: dict, crop: Crop, docs: list[dict], seedlings: int = HABIT_SEEDLINGS) -> dict:
    docs = sorted(docs, key=lambda d: d["seq"])
    weekday = HABIT_WEEKDAY
    setup_ids = {b["id"] for b in ref["batches"]}

    real = initial(ref, meta)
    real_got: dict[str, float] = {}
    real_shut: dict[str, date] = {}
    _close(current_crop(real, crop), real, real_shut)
    for doc in docs:
        for ev in doc["events"]:
            apply(real, crop, ev)
            if ev["t"] == "harvest":
                real_got[ev["batch"]] = real_got.get(ev["batch"], 0.0) + ev["kg"]
            elif ev["t"] == "clock":
                _close(current_crop(real, crop), real, real_shut)
    c = current_crop(real, crop)

    hab = initial(ref, meta)
    hab.curve = real.curve
    hab_got: dict[str, float] = {}
    hab_shut: dict[str, date] = {}
    short = 0.0

    def sow_habit() -> None:
        if hab.today.weekday() == weekday:
            for ln in crop.lines:
                apply(hab, c, {"t": "sow", "line": ln.id, "day": hab.today.isoformat(), "seedlings": seedlings})

    sow_habit()
    _close(c, hab, hab_shut)
    for doc in docs:
        for ev in doc["events"]:
            t = ev["t"]
            if t in ("sow", "reference_reset"):
                continue
            if t == "harvest":
                line = real.batches[ev["batch"]].line
                d = date.fromisoformat(ev["day"])
                open_ = [b for b in hab.batches.values() if b.line == line and b.id not in hab_shut]
                taken = take_oldest(c, open_, d, ev["kg"])
                for b, kg in taken:
                    hab_got[b.id] = hab_got.get(b.id, 0.0) + kg
                short += ev["kg"] - sum(kg for _, kg in taken)
            elif t == "loss" and ev.get("recount"):
                continue                     # "seen left" fixes the real bed's count; the habit's beds keep theirs
            elif t == "loss":
                sown = real.batches[ev["batch"]]
                same = [b for b in hab.batches.values()
                        if b.line == sown.line and b.sown_on <= hab.today and b.id not in hab_shut]
                if same:
                    b = min(same, key=lambda b: (abs((b.sown_on - sown.sown_on).days), b.id))
                    hab.batches[b.id] = apply_loss(c, b, date.fromisoformat(ev["day"]), ev["pct"])
            else:
                apply(hab, c, ev)
                if t == "clock":
                    sow_habit()
                    _close(c, hab, hab_shut)

    beds = ([_bed(c, b, real_shut, "before" if b.id in setup_ids else "tanam") for b in real.batches.values()]
            + [_bed(c, b, hab_shut, "habit") for b in hab.batches.values() if b.id not in setup_ids])
    beds.sort(key=lambda b: (b["sown_on"], b["id"]))
    group = lambda g: [b for b in beds if b["group"] == g]  # noqa: E731
    return {
        "today": real.today.isoformat(),
        "habit": {"seedlings": seedlings, "weekday": weekday},
        "rows": {"before": _row(group("before"), real_got), "tanam": _row(group("tanam"), real_got),
                 "habit": _row(group("habit"), hab_got)},
        "delivery": {"logged_kg": round(sum(real_got.values()), 2), "habit_kg": round(sum(hab_got.values()), 2),
                     "habit_short_kg": round(short, 2)},
        "beds": beds,
    }
