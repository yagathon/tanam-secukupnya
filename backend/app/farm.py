"""A visitor's farm: reference data + their event log, replayed, and the views the API serves.

The crop and the truth world are process-wide. A visitor's state is rebuilt by replaying their
`events` log over the reference data; the result (and the engine's plans for it) is cached per
visitor and keyed by the log, so the five views of one screen share one replay.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from functools import lru_cache

from app import engine, notes, sandbox, sim
from app import world as W
from app.allocator import BuyerOrder, HouseholdOrder, allocate_day
from app.growth import Crop, crop_from_dict, first_ready_day
from app.production import (
    available_kg,
    avg_g,
    bed_day,
    in_bed_plants,
    project,
    spread,
    waste_plants,
)
from app.state import FarmState, apply, current_crop, replay
from app.store import SEED_DIR, Store

CHART_DAYS = 40
SEASON_FILE = SEED_DIR / "season.json"
_CACHE_SIZE = 256


@lru_cache(maxsize=64)
def _crop(raw: str) -> Crop:
    return crop_from_dict(json.loads(raw))


def crop(ws: Store) -> Crop:
    """One Crop object per crop definition, so production's per-crop lookup cache stays warm."""
    return _crop(json.dumps(ws.list("crops")[0], sort_keys=True))


def world(ws: Store) -> W.World:
    return W.build(int(ws.meta()["seed"]))


@dataclass
class View:
    state: FarmState
    plans: dict[str, sim.LinePlan]
    log_key: tuple[int, int]
    crop: Crop
    rev: str | None = None           # sandbox setup revision: a setup edit invalidates the view
    digest: str = ""                 # log content: a clear refilled to the same seqs invalidates it


_views: OrderedDict[str, View] = OrderedDict()


def replay_check(ws: Store) -> None:
    """Raise KeyError/ValueError if ws's log does not replay on ws's reference."""
    replay({"batches": ws.list("batches"), "history": ws.list("history")}, ws.meta(), crop(ws), ws.list("events"))


def log_key(docs: list[dict]) -> tuple[int, int]:
    return len(docs), max((d["seq"] for d in docs), default=0)


def doc_print(doc: dict) -> str:
    """Content fingerprint of one log entry: a cleared log refilled to the same seqs differs here."""
    return hashlib.blake2b(json.dumps(doc, sort_keys=True, default=str).encode(), digest_size=8).hexdigest()


def log_digest(docs: list[dict]) -> str:
    return hashlib.blake2b("".join(doc_print(d) for d in docs).encode(), digest_size=8).hexdigest()


def load(ws: Store) -> View:
    """The visitor's state and today's plans (cached until their log changes). Treat as read-only."""
    docs = ws.list("events")
    key = log_key(docs)
    hit = _views.get(ws.uid)
    rev, digest = ws.meta().get("rev"), log_digest(sorted(docs, key=lambda d: d["seq"]))
    if hit is not None and hit.log_key == key and hit.rev == rev and hit.digest == digest:
        _views.move_to_end(ws.uid)
        return hit
    c = crop(ws)
    st = replay({"batches": ws.list("batches"), "history": ws.list("history")}, ws.meta(), c, docs)
    view = View(st, sim.plan(st, c, ws.list("buyers")), key, current_crop(st, c), rev, digest)
    _views[ws.uid] = view
    while len(_views) > _CACHE_SIZE:
        _views.popitem(last=False)
    return view


def append(ws: Store, seq: int, doc: dict) -> bool:
    """Write log entry `seq`, only if no entry has that seq yet. `seq` comes from the state the caller
    checked (its log_key + 1), so of two requests that read the same log only the first writes."""
    return ws.add("events", {**doc, "id": f"e{seq:08d}", "seq": seq})


# --- day loop ---

def next_day(ws: Store, from_day: date, days: int) -> dict:
    """Append `days` simulated days to the log, starting only if the visitor is still on `from_day`
    (a double-click or a retried request then appends nothing)."""
    v = load(ws)
    if v.state.today != from_day:
        return {"today": v.state.today.isoformat(), "appended": 0}
    c = crop(ws)
    if ws.meta().get("sandbox"):
        if sum(1 for d in ws.list("events") if d["kind"] == "day") + days > sandbox.MAX_DAYS:
            raise ValueError(f"the sandbox holds at most {sandbox.MAX_DAYS} days; clear it to start again")
        buyers, hh = ws.list("buyers"), ws.list("households")
        def step(st, plans):
            return sandbox.close_day(st, current_crop(st, c), buyers, hh, plans)
    else:
        w, fixed = world(ws), ws.meta()["fixed_seedlings"]
        def step(st, plans):
            return sim.day_events(st, c, w, "tanam", fixed, plans)
    st, plans = copy.deepcopy(v.state), v.plans
    seq = v.log_key[1] + 1
    for i in range(days):
        if i:
            plans = sim.plan(st, current_crop(st, c), ws.list("buyers"))
        evs = step(st, plans)
        if not append(ws, seq + i, {"kind": "day", "events": evs}):
            return {"today": load(ws).state.today.isoformat(), "appended": i}
        for ev in evs:
            apply(st, c, ev)
    return {"today": st.today.isoformat(), "appended": days}



def reference(ws: Store) -> dict:
    v, base = load(ws), crop(ws)
    kept = v.state.ref_kept or tuple(() for _ in base.curve)
    return {"start": [list(p) for p in base.curve], "now": [[x, round(y, 1)] for x, y in v.crop.curve],
            "samples": [len(k) for k in kept]}


# --- views ---

def _alias(ws: Store) -> dict[str, str]:
    return {r["id"]: r["alias"] for r in ws.list("buyers") + ws.list("households")}


def _tomorrow_orders(ws: Store, st: FarmState, lp: sim.LinePlan) -> tuple[list[BuyerOrder], list[HouseholdOrder]]:
    """Who is expected to take this line tomorrow: buyers at their known order (else expected), and the
    households subscribed for tomorrow's weekday sharing the household forecast evenly."""
    tom = st.today + timedelta(days=1)
    mins = {b["id"]: b["lines"].get(lp.line, {}).get("min_kg", 0.0) for b in ws.list("buyers")}
    buyers = [BuyerOrder(k.split(":")[1], round(kg, 2), mins.get(k.split(":")[1], 0.0))
              for k, kg in lp.needs.tomorrow_parts.items() if k.startswith("b2b:") and kg > 0]
    if st.household_ids:                     # sandbox: households' orders are entered, not simulated
        hh = [HouseholdOrder(who, kg, st.last_shorted.get(who)) for (iso, who, l2), kg in sorted(st.known_orders.items())
              if iso == tom.isoformat() and l2 == lp.line and who in st.household_ids and kg > 0]
        return buyers, hh
    subs = [h for h in ws.list("households") if h["line"] == lp.line and tom.weekday() in h["weekdays"]]
    hh_kg = lp.needs.tomorrow_parts.get(engine.hh_key(lp.line), 0.0)
    each = round(hh_kg / len(subs), 2) if subs else 0.0
    hh = [HouseholdOrder(h["id"], each, st.last_shorted.get(h["id"])) for h in subs]
    return buyers, hh


def tomorrow(ws: Store) -> dict:
    v = load(ws)
    st, names = v.state, _alias(ws)
    tom = st.today + timedelta(days=1)
    lines = []
    for lp in v.plans.values():
        buyers, hh = _tomorrow_orders(ws, st, lp)
        rows_b, rows_h = allocate_day(lp.send, buyers, hh, tom)
        lines.append({
            "line": lp.line, "day": tom.isoformat(), "need_kg": round(lp.needs.tomorrow, 2),
            "available_kg": lp.available_tomorrow, "ceiling_kg": lp.ceiling, "send_kg": lp.send,
            "short_kg": round(max(0.0, lp.needs.tomorrow - lp.send), 2),
            "buyers": [{"id": r.customer_id, "alias": names.get(r.customer_id, r.customer_id),
                        "known": r.customer_id in lp.needs.known, "ordered_kg": round(r.ordered_kg, 2),
                        "served_kg": round(r.served_kg, 2), "min_kg": next(b.min_kg for b in buyers if b.buyer_id == r.customer_id)}
                       for r in rows_b],
            "households": [{"id": r.customer_id, "alias": names.get(r.customer_id, r.customer_id),
                            "ordered_kg": round(r.ordered_kg, 2), "served_kg": round(r.served_kg, 2)} for r in rows_h],
            "borrowing": lp.borrowing,
        })
    return {"today": st.today.isoformat(), "lines": lines}


def beds(ws: Store) -> dict:
    v = load(ws)
    st, c = v.state, v.crop
    tom = st.today + timedelta(days=1)
    lines = []
    for lp in v.plans.values():
        ln = c.line(lp.line)
        rows = []
        for b in sorted(st.alive(c, lp.line), key=lambda b: b.sown_on):
            bd = bed_day(c, b, st.today)
            rows.append({
                "id": b.id, "label": b.label, "sown_on": b.sown_on.isoformat(), "bed_day": bd,
                "stage": "nursery" if bd < 0 else "bed", "seedlings": b.seedlings,
                "plants_left": round(in_bed_plants(c, b, st.today)),
                "avg_g": round(avg_g(c, b, st.today)) if bd >= 0 else None,
                "size_pct": round(b.size_factor * 100), "spread": round(spread(c, b), 2), "sampled": b.sampled,
                "ready_from": first_ready_day(c, ln, b.sown_on, b.size_factor, b.spread_ratio).isoformat(),
                "until": (b.sown_on + timedelta(days=c.nursery_days + c.max_bed_day)).isoformat(),
                "available_tomorrow_kg": round(available_kg(c, b, tom), 2),
                "waste_plants": round(waste_plants(c, b, st.today)),
            })
        proj = project(c, lp.line, st.alive(c, lp.line), lp.needs.protected, tom, tom + timedelta(days=CHART_DAYS - 1))
        chart = [{"day": p.day.isoformat(), "available_kg": round(p.available_kg, 2), "need_kg": round(p.need_kg, 2),
                  "short_kg": round(p.short_kg, 2)} for p in proj]
        lines.append({"line": lp.line, "min_g": ln.min_g, "max_g": ln.max_g, "batches": rows, "chart": chart})
    return {"today": st.today.isoformat(), "lines": lines}


def sow(ws: Store) -> dict:
    v = load(ws)
    st, c = v.state, v.crop
    lines = []
    for lp in v.plans.values():
        p = asdict(lp.sow)
        p = {k: (x.isoformat() if isinstance(x, date) else x) for k, x in p.items()}
        missed = engine.missed_slots(st.last_sown.get(lp.line), lp.sow.day, c.sow_weekdays)
        lines.append({**p, "missed": [d.isoformat() for d in missed],
                      "postponed": [{"day": d, "reason": r} for (ln, d), r in st.postponed.items() if ln == lp.line],
                      "basis": {"need": "B2B high + households high", "survival": c.survival,
                                "germination": c.germination, "seeds_per_gram": c.seeds_per_gram,
                                "grams_per_teaspoon": c.grams_per_teaspoon, "max_seedlings": c.max_seedlings}})
    return {"today": st.today.isoformat(), "lines": lines}


def demand(ws: Store) -> dict:
    v = load(ws)
    st, names = v.state, _alias(ws)
    model = sim.demand_model(st)
    series = []
    for k, f in model.fits.items():
        kind, *rest = k.split(":")
        label = names.get(rest[0], rest[0]) if kind == "b2b" else f"Households ({rest[0]})"
        series.append({"key": k, "label": label, "line": rest[-1], "usual_kg": round(f.usual, 2),
                       "level_kg": round(f.level, 2), "shape": f.shape})
    m = model.market
    text = (f"Market {round((m - 1) * 100):+d}% across {model.market_buyers} buyers this week (cause unknown)"
            if m != 1 else f"No market-wide move ({model.market_buyers} buyers checked)")
    return {"today": st.today.isoformat(), "market": {"factor": m, "buyers": model.market_buyers, "text": text},
            "series": series, "signals": st.signals,
            "lines": [{"line": lp.line, "days": lp.needs.rows} for lp in v.plans.values()]}


def today(ws: Store) -> dict:
    v = load(ws)
    st = v.state
    t = tomorrow(ws)
    out = []
    for lp, tl in zip(v.plans.values(), t["lines"]):
        s = lp.sow
        out.append({"line": lp.line, "need_kg": tl["need_kg"], "ceiling_kg": lp.ceiling, "send_kg": lp.send,
                    "short_kg": tl["short_kg"],
                    "rotated": [h["alias"] for h in tl["households"] if h["served_kg"] < h["ordered_kg"]],
                    "sow": {"day": s.day.isoformat(), "weekday": s.day.strftime("%a"), "seedlings": s.seedlings,
                            "seeds_g": s.seeds_g, "teaspoons": s.teaspoons,
                            "shortfall_ahead_kg": round(sum(r["kg"] for r in s.shortfall_ahead), 2)}})
    pending = [n for n in ws.list("notes") if n.get("status") == "proposed"]
    return {"today": st.today.isoformat(), "weekday": st.today.strftime("%A"), "lines": out, "pending": pending}


def note_inputs(ws: Store) -> dict:
    """What reading and sanitizing a note needs: the Gemini context, bed label → batch id, the sowing
    day a "postponed" note refers to (per line), and the log seq an accepted note would take."""
    v = load(ws)
    st, c = v.state, v.crop
    in_ground = [b for b in sorted(st.alive(c), key=lambda b: b.sown_on)
                 if bed_day(c, b, st.today) >= 0 and in_bed_plants(c, b, st.today) > 0]
    model = sim.demand_model(st)
    usual = {k.removeprefix("b2b:"): round(f.level * model.market, 1) for k, f in model.fits.items() if k.startswith("b2b:")}
    lines = [ln.id for ln in c.lines]
    ctx = notes.context(st.today, ws.list("buyers"),
                        [{"label": b.label, "line": b.line, "bed_day": bed_day(c, b, st.today)} for b in in_ground],
                        lines, usual)
    return {"today": st.today, "ctx": ctx, "beds": {b.label: b.id for b in in_ground}, "lines": lines,
            "max_seedlings": c.max_seedlings,
            "next_sow": {ln: engine.next_sow_day(st.today, st.last_sown.get(ln) == st.today
                                                 or (ln, st.today.isoformat()) in st.postponed, c.sow_weekdays) for ln in lines},
            "seq": v.log_key[1] + 1}


def check_events(ws: Store, events: list[dict]) -> None:
    """Raise ValueError if the events cannot be applied to the visitor's current state."""
    st = copy.deepcopy(load(ws).state)
    for ev in events:
        apply(st, crop(ws), ev)


def season() -> dict:
    return json.loads(SEASON_FILE.read_text()) if SEASON_FILE.exists() else {"runs": [], "summary": {}}
