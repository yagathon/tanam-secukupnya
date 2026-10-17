"""Impact: the sandbox as logged vs. the same days under the old habit (a fixed sowing once a week).

The habit run replays the log with three changes: its own sowing replaces every logged one, each day's
harvested kg (logged or assumed) is taken oldest bed first from its beds, and a logged loss hits its bed
closest in age. Orders and the reference curve are the farm's own (the habit grows on the final learned
curve), so the two runs differ only in what was sown. Waste = plants that outgrew the line unharvested.
"""

from __future__ import annotations

from datetime import date

from app.growth import Crop
from app.production import Batch, apply_loss, in_bed_plants, take_oldest, waste_plants
from app.state import FarmState, apply, current_crop, initial

HABIT_SEEDLINGS = 1000


def _row(c: Crop, st: FarmState, beds: list[Batch], delivered: dict[str, float]) -> dict:
    harvested = sum(b.harvested_plants for b in beds)
    waste = sum(waste_plants(c, b, st.today) for b in beds)
    return {"beds": len(beds), "seedlings": sum(b.seedlings for b in beds), "harvested_plants": round(harvested),
            "lost_plants": round(sum(b.lost_plants for b in beds)), "waste_plants": round(waste),
            "in_field_plants": round(sum(in_bed_plants(c, b, st.today) for b in beds)),
            "waste_pct": round(100 * waste / (harvested + waste), 1) if harvested + waste > 0.5 else 0.0,
            "delivered_kg": round(sum(delivered.get(b.id, 0.0) for b in beds), 2)}


def _total_waste(c: Crop, st: FarmState) -> float:
    return sum(waste_plants(c, b, st.today) for b in st.batches.values())


def build(ref: dict, meta: dict, crop: Crop, docs: list[dict], seedlings: int = HABIT_SEEDLINGS) -> dict:
    docs = sorted(docs, key=lambda d: d["seq"])
    weekday = crop.sow_weekdays[0]
    setup_ids = {b["id"] for b in ref["batches"]}

    real = initial(ref, meta)
    real_got: dict[str, float] = {}
    days = [real.today]
    real_series = [_total_waste(current_crop(real, crop), real)]
    for doc in docs:
        for ev in doc["events"]:
            apply(real, crop, ev)
            if ev["t"] == "harvest":
                real_got[ev["batch"]] = real_got.get(ev["batch"], 0.0) + ev["kg"]
            elif ev["t"] == "clock":
                days.append(real.today)
                real_series.append(_total_waste(current_crop(real, crop), real))
    c = current_crop(real, crop)

    hab = initial(ref, meta)
    hab.curve = real.curve
    hab_got: dict[str, float] = {}
    short = 0.0

    def sow_habit() -> None:
        if hab.today.weekday() == weekday:
            for ln in crop.lines:
                apply(hab, c, {"t": "sow", "line": ln.id, "day": hab.today.isoformat(), "seedlings": seedlings})

    sow_habit()
    hab_series = [_total_waste(c, hab)]
    for doc in docs:
        for ev in doc["events"]:
            t = ev["t"]
            if t in ("sow", "reference_reset"):
                continue
            if t == "harvest":
                line = real.batches[ev["batch"]].line
                d = date.fromisoformat(ev["day"])
                taken = take_oldest(c, [b for b in hab.batches.values() if b.line == line], d, ev["kg"])
                for b, kg in taken:
                    hab_got[b.id] = hab_got.get(b.id, 0.0) + kg
                short += ev["kg"] - sum(kg for _, kg in taken)
            elif t == "loss":
                sown = real.batches[ev["batch"]]
                same = [b for b in hab.batches.values() if b.line == sown.line and b.sown_on <= hab.today]
                if same:
                    b = min(same, key=lambda b: (abs((b.sown_on - sown.sown_on).days), b.id))
                    hab.batches[b.id] = apply_loss(c, b, date.fromisoformat(ev["day"]), ev["pct"])
            else:
                apply(hab, c, ev)
                if t == "clock":
                    sow_habit()
                    hab_series.append(_total_waste(c, hab))

    delivered = sum(real_got.values())
    return {
        "today": real.today.isoformat(),
        "habit": {"seedlings": seedlings, "weekday": weekday},
        "rows": {
            "before": _row(c, real, [b for b in real.batches.values() if b.id in setup_ids], real_got),
            "tanam": _row(c, real, [b for b in real.batches.values() if b.id not in setup_ids], real_got),
            "habit": _row(c, hab, [b for b in hab.batches.values() if b.id not in setup_ids], hab_got),
        },
        "delivery": {"logged_kg": round(delivered, 2), "habit_kg": round(sum(hab_got.values()), 2),
                     "habit_short_kg": round(short, 2)},
        "series": [{"day": d.isoformat(), "tanam_waste": round(a), "habit_waste": round(b)}
                   for d, a, b in zip(days, real_series, hab_series)],
    }
