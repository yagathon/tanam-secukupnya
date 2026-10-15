"""The day loop: today's engine view, the events of one simulated day, warm-up, and the season run.

`plan` is what the API shows. `day_events` is what "Next day →" appends and what the season sim
steps through; it reads the truth world for what actually happens (orders, growth, rain, pests).
"""

from __future__ import annotations

import copy
import statistics
from dataclasses import dataclass, replace
from datetime import date, timedelta

from app import demand, engine
from app import world as W
from app.allocator import BuyerOrder, HouseholdOrder, allocate_day
from app.growth import Crop, curve
from app.production import (
    Batch,
    available_kg,
    bed_day,
    in_bed_plants,
    plants0,
    take_oldest,
    waste_plants,
)
from app.state import FarmState, apply

PLAN_DAYS = 45
STRATEGIES = ("cobweb", "fixed", "tanam")


@dataclass
class LinePlan:
    line: str
    needs: engine.LineNeeds
    available_tomorrow: float
    ceiling: float
    send: float
    borrowing: list[dict]
    sow: engine.SowPlan


def demand_model(st: FarmState) -> demand.DemandModel:
    return demand.fit(st.history, W.DAY0, st.today + timedelta(days=1))


def plan(st: FarmState, crop: Crop, buyers: list[dict], model: demand.DemandModel | None = None) -> dict[str, LinePlan]:
    model = model or demand_model(st)
    out = {}
    tom = st.today + timedelta(days=1)
    for ln in crop.lines:
        batches = st.alive(crop, ln.id)
        sown_today = st.last_sown.get(ln.id) == st.today or (ln.id, st.today.isoformat()) in st.postponed
        end = engine.horizon_end(crop, ln.id, st.today, sown_today)
        needs = engine.line_needs(model, buyers, ln.id, st.today, st.today + timedelta(days=PLAN_DAYS),
                                  st.known_orders, st.signals)
        ceil = engine.ceiling(crop, ln.id, batches, needs.protected, st.today, end)
        avail = round(sum(available_kg(crop, b, tom) for b in batches), 2)
        send = min(needs.tomorrow, ceil)
        borrow = engine.borrowing(crop, ln.id, batches, needs.protected, st.today, end, min(needs.tomorrow, avail), ceil) \
            if needs.tomorrow > ceil + engine.EPS_KG else []
        sow = engine.sow_next(crop, ln.id, batches, needs.protected, needs.target, st.today,
                              st.last_sown.get(ln.id), sown_today)
        out[ln.id] = LinePlan(ln.id, needs, avail, ceil, round(send, 2), borrow, sow)
    return out


def _truth(crop: Crop, w: W.World, b: Batch) -> Batch:
    size, r = w.growth_truth(crop, b.line, b.sown_on)
    return replace(b, size_factor=size, spread_ratio=r)


def _sample(crop: Crop, b: Batch, d: date) -> tuple[float, float]:
    """5 biggest and 5 smallest weighed together (true growth; the 5 extremes sit ~90% out on the spread)."""
    avg = b.size_factor * curve(crop, bed_day(crop, b, d))
    k = 0.9 * b.spread_ratio / 2
    return round(5 * avg * (1 + k)), round(5 * avg * (1 - k))


def _cobweb(st: FarmState, crop: Crop, w: W.World, line: str, fixed: int) -> int:
    last = next((s["seedlings"] for s in reversed(st.sowings) if s["line"] == line), fixed)
    week = [s for s in st.served if s["line"] == line and (st.today - date.fromisoformat(s["day"])).days < 7]
    ordered = sum(s["b2b_ordered"] + s["hh_ordered"] for s in week)
    served = sum(s["b2b_served"] + s["hh_served"] for s in week)
    short = (ordered - served) / ordered if ordered else 0.0
    waste = sum(s.get("waste_kg", 0.0) for s in week) / ordered if ordered else 0.0
    f = 1 + 0.5 * short if short >= waste else 1 - 0.5 * waste
    return int(max(0, min(crop.max_seedlings, round(last * f / engine.SEEDLING_STEP) * engine.SEEDLING_STEP)))


def day_events(st: FarmState, crop: Crop, w: W.World, strategy: str, fixed: dict[str, int],
               plans: dict[str, LinePlan] | None = None) -> list[dict]:
    """Everything that happens from today (t) to tomorrow (t+1), as primitive events."""
    t = st.today
    d = t + timedelta(days=1)
    evs: list[dict] = []
    buyers = {b["id"]: b for b in w.buyers}
    if strategy == "tanam" and plans is None:
        plans = plan(st, crop, list(w.buyers))
    for ln in crop.lines:
        line = ln.id
        b2b = [BuyerOrder(b, kg, buyers[b]["lines"][line]["min_kg"])
               for (iso, b, l2), kg in sorted(st.known_orders.items()) if iso == d.isoformat() and l2 == line]
        hh = [HouseholdOrder(h, kg, st.last_shorted.get(h)) for h, l2, kg in w.hh.get(d.isoformat(), []) if l2 == line]
        need = sum(o.kg for o in b2b) + sum(o.kg for o in hh)
        x = min(need, plans[line].ceiling) if strategy == "tanam" else need
        shadows = [_truth(crop, w, b) for b in st.alive(crop, line)]
        w0 = sum(waste_plants(crop, b, t) for b in shadows)
        got = 0.0
        for b, kg in take_oldest(crop, shadows, d, x):
            big5, small5 = _sample(crop, b, d)
            evs.append({"t": "harvest", "batch": b.id, "day": d.isoformat(), "kg": round(kg, 2),
                        "big5_g": big5, "small5_g": small5})
            got += round(kg, 2)
        w1 = sum(waste_plants(crop, b, d) for b in shadows)
        rows_b, rows_h = allocate_day(got, b2b, hh, d)
        evs += [{"t": "short", "household": r.customer_id, "day": d.isoformat()} for r in rows_h if r.short_kg > 0]
        evs.append({"t": "served", "day": d.isoformat(), "line": line,
                    "b2b_ordered": round(sum(r.ordered_kg for r in rows_b), 2), "b2b_served": round(sum(r.served_kg for r in rows_b), 2),
                    "hh_ordered": round(sum(r.ordered_kg for r in rows_h), 2), "hh_served": round(sum(r.served_kg for r in rows_h), 2),
                    "waste_kg": round(max(0.0, w1 - w0) * (ln.min_g + ln.max_g) / 2000, 2)})
        for b in w.buyers:
            if line in b["lines"] and (kg := w.series_actual(engine.b2b_key(b["id"], line), d)) is not None:
                evs.append({"t": "actual", "series": engine.b2b_key(b["id"], line), "day": d.isoformat(), "kg": kg})
        evs.append({"t": "actual", "series": engine.hh_key(line), "day": d.isoformat(),
                    "kg": w.series_actual(engine.hh_key(line), d)})
    nxt = (d + timedelta(days=1)).isoformat()
    evs += [{"t": "order", "day": iso, "buyer": b, "line": line, "kg": kg}
            for (iso, b, line), kg in sorted(w.b2b.items()) if iso == nxt]
    if t.weekday() in crop.sow_weekdays:
        for ln in crop.lines:
            if st.last_sown.get(ln.id) == t or (ln.id, t.isoformat()) in st.postponed:
                continue
            if t in W.RAIN_DAYS:
                evs.append({"t": "postpone", "line": ln.id, "day": t.isoformat(), "reason": "rain"})
                continue
            n = (plans[ln.id].sow.seedlings if strategy == "tanam" else
                 fixed[ln.id] if strategy == "fixed" else _cobweb(st, crop, w, ln.id, fixed[ln.id]))
            if n > 0:
                evs.append({"t": "sow", "line": ln.id, "day": t.isoformat(), "seedlings": n})
    pday, pline, pct, cause = W.PEST
    if t == pday:
        beds = [b for b in st.alive(crop, pline) if bed_day(crop, b, t) >= 0 and in_bed_plants(crop, b, t) > 0]
        if beds:
            oldest = min(beds, key=lambda b: (b.sown_on, b.id))
            evs.append({"t": "loss", "batch": oldest.id, "day": t.isoformat(), "pct": pct, "cause": cause})
    evs.append({"t": "clock", "day": d.isoformat()})
    return evs


def step(st: FarmState, crop: Crop, w: W.World, strategy: str, fixed: dict[str, int]) -> list[dict]:
    evs = day_events(st, crop, w, strategy, fixed)
    for ev in evs:
        apply(st, crop, ev)
    return evs


def fixed_seedlings(crop: Crop, w: W.World) -> dict[str, int]:
    """The fixed farmer's every-Mon/Thu sowing: history's mean daily demand × 3.5 days, in seedlings."""
    out = {}
    hist = [W.DAY0 - timedelta(days=i) for i in range(1, W.HISTORY_DAYS + 1)]
    for ln in crop.lines:
        keys = [engine.b2b_key(b["id"], ln.id) for b in w.buyers if ln.id in b["lines"]] + [engine.hh_key(ln.id)]
        daily = statistics.fmean(sum(w.series_actual(k, d) or 0.0 for k in keys) for d in hist)
        kg_per_plant = (ln.min_g + ln.max_g) / 2000
        n = daily * 3.5 / kg_per_plant / crop.survival
        out[ln.id] = int(round(n / engine.SEEDLING_STEP) * engine.SEEDLING_STEP)
    return out


def warmup(crop: Crop, w: W.World) -> tuple[FarmState, dict[str, int]]:
    """Run the farm (fixed sowing) from START to DAY0, then trim history to the last 8 weeks."""
    fixed = fixed_seedlings(crop, w)
    st = FarmState(W.START, {}, {}, {})
    for (iso, b, line), kg in w.b2b.items():
        if iso == (W.START + timedelta(days=1)).isoformat():
            st.known_orders[iso, b, line] = kg
    while st.today < W.DAY0:
        step(st, crop, w, "fixed", fixed)
    cut = W.DAY0 - timedelta(days=W.HISTORY_DAYS)
    st.history = {k: {d: v for d, v in s.items() if d >= cut} for k, s in st.history.items()}
    st.batches = {k: b for k, b in st.batches.items() if b in st.alive(crop)}
    st.known_orders = {k: v for k, v in st.known_orders.items() if k[0] > W.DAY0.isoformat()}
    st.served, st.sowings = [], []
    return st, fixed


def season(crop: Crop, w: W.World, strategy: str, days: int = W.FUTURE_DAYS,
           start: tuple[FarmState, dict[str, int]] | None = None) -> dict:
    st0, fixed = start or warmup(crop, w)
    st = copy.deepcopy(st0)
    first = set(st.batches)
    for _ in range(days):
        step(st, crop, w, strategy, fixed)
    end = st.today
    done = [b for k, b in st.batches.items() if k not in first
            and (end - b.sown_on).days > crop.nursery_days + crop.max_bed_day]
    p0 = sum(plants0(crop, b) for b in done)
    left = sum(max(0.0, plants0(crop, b) - b.harvested_plants - b.lost_plants) for b in done)
    tot = lambda f: sum(s[f] for s in st.served)  # noqa: E731
    seeds = [s["seedlings"] for s in st.sowings if s["line"] == "regular"]
    return {
        "strategy": strategy, "seed": w.seed,
        "waste_pct": round(100 * left / p0, 1) if p0 else 0.0,
        "b2b_fill_pct": round(100 * tot("b2b_served") / tot("b2b_ordered"), 1) if tot("b2b_ordered") else 100.0,
        "hh_fill_pct": round(100 * tot("hh_served") / tot("hh_ordered"), 1) if tot("hh_ordered") else 100.0,
        "sowing_cv": round(statistics.pstdev(seeds) / statistics.fmean(seeds), 2) if seeds else 0.0,
        "sowings": [s for s in st.sowings if s["line"] == "regular"],
    }
