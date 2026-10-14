"""Visitor state = seed + an ordered event log, rebuilt by replaying the log (deterministic).

Each workspace `events` doc is {"seq", "kind": "day"|"note", "events": [primitive events]}.
Primitive events (field "t"):
  clock{day} · actual{series,day,kg} · order{day,buyer,line,kg} · harvest{batch,day,kg,big5_g?,small5_g?}
  sow{line,day,seedlings} · postpone{line,day,reason} · loss{batch,day,pct,cause} · short{household,day}
  served{day,line,b2b_ordered,b2b_served,hh_ordered,hh_served} · signal{scope,line,effect_pct,date_from,date_to,cause}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.growth import Crop
from app.production import Batch, apply_loss, apply_sample, harvest


@dataclass
class FarmState:
    today: date
    batches: dict[str, Batch]
    history: dict[str, dict[date, float]]
    known_orders: dict[tuple[str, str, str], float]
    last_shorted: dict[str, date] = field(default_factory=dict)
    signals: list[dict] = field(default_factory=list)
    last_sown: dict[str, date] = field(default_factory=dict)
    postponed: dict[tuple[str, str], str] = field(default_factory=dict)
    served: list[dict] = field(default_factory=list)
    sowings: list[dict] = field(default_factory=list)
    next_bed: int = 1

    def alive(self, crop: Crop, line: str | None = None) -> list[Batch]:
        """Batches not yet past max_bed_day + 1 (older ones can't serve anything)."""
        return [b for b in self.batches.values() if (line is None or b.line == line)
                and (self.today - b.sown_on).days <= crop.nursery_days + crop.max_bed_day + 1]


def initial(ref: dict, meta: dict) -> FarmState:
    """From the reference data: today, beds on DAY0, order history, the orders known for tomorrow."""
    batches = {b["id"]: Batch.from_dict(b) for b in ref["batches"]}
    history: dict[str, dict[date, float]] = {}
    known: dict[tuple[str, str, str], float] = {}
    for row in ref["history"]:
        d = date.fromisoformat(row["id"])
        for k, v in row["series"].items():
            history.setdefault(k, {})[d] = v
        for k, v in row.get("orders", {}).items():
            buyer, line = k.split(":")
            known[row["id"], buyer, line] = v
    st = FarmState(date.fromisoformat(meta["day0"]), batches, history, known,
                   last_sown={k: date.fromisoformat(v) for k, v in meta["last_sown"].items()},
                   next_bed=int(meta["next_bed"]))
    return st


def to_ref(st: FarmState) -> tuple[dict, dict]:
    """Inverse of `initial`: the reference data (batches, history docs) and meta that rebuild `st`."""
    days: dict[str, dict] = {}
    for k, s in st.history.items():
        for d, v in s.items():
            days.setdefault(d.isoformat(), {"id": d.isoformat(), "series": {}, "orders": {}})["series"][k] = v
    for (iso, buyer, line), kg in st.known_orders.items():
        days.setdefault(iso, {"id": iso, "series": {}, "orders": {}})["orders"][f"{buyer}:{line}"] = kg
    ref = {"batches": [b.to_dict() for b in st.batches.values()], "history": [days[k] for k in sorted(days)]}
    meta = {"day0": st.today.isoformat(), "last_sown": {k: v.isoformat() for k, v in st.last_sown.items()},
            "next_bed": st.next_bed}
    return ref, meta


def apply(st: FarmState, crop: Crop, ev: dict) -> None:
    t = ev["t"]
    d = date.fromisoformat(ev["day"]) if "day" in ev else None
    if t == "clock":
        st.today = d
    elif t == "actual":
        st.history.setdefault(ev["series"], {})[d] = ev["kg"]
    elif t == "order":
        st.known_orders[ev["day"], ev["buyer"], ev["line"]] = ev["kg"]
    elif t == "harvest":
        b = st.batches[ev["batch"]]
        if ev.get("big5_g") and ev.get("small5_g"):
            st.batches[b.id] = apply_sample(crop, b, d, ev["kg"], ev["big5_g"], ev["small5_g"])
        else:
            st.batches[b.id] = harvest(crop, b, d, ev["kg"])
    elif t == "sow":
        bid = f"{ev['line']}-{ev['day']}"
        if bid in st.batches:  # a second sowing note for the same line and day adds to that batch
            b = st.batches[bid]
            b.seedlings += int(ev["seedlings"])
        else:
            st.batches[bid] = Batch(bid, f"Bed {st.next_bed}", ev["line"], d, int(ev["seedlings"]))
            st.next_bed += 1
        st.last_sown[ev["line"]] = max(d, st.last_sown.get(ev["line"], d))
        st.postponed.pop((ev["line"], ev["day"]), None)
        st.sowings.append({"line": ev["line"], "day": ev["day"], "seedlings": int(ev["seedlings"])})
    elif t == "postpone":
        st.postponed[ev["line"], ev["day"]] = ev.get("reason", "")
    elif t == "loss":
        b = st.batches[ev["batch"]]
        st.batches[b.id] = apply_loss(crop, b, d, ev["pct"])
    elif t == "short":
        st.last_shorted[ev["household"]] = d
    elif t == "served":
        st.served.append(ev)
    elif t == "signal":
        st.signals.append(ev)
    else:
        raise ValueError(f"unknown event {t!r}")


def replay(ref: dict, meta: dict, crop: Crop, docs: list[dict]) -> FarmState:
    st = initial(ref, meta)
    for doc in sorted(docs, key=lambda x: x["seq"]):
        for ev in doc["events"]:
            apply(st, crop, ev)
    return st
