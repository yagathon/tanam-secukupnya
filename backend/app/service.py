"""Glue between the store and the pure logic: build the inputs, run, shape the outputs.

No I/O beyond the store, no Gemini: the AI steps (notes → signals, messages, explanations) plug in
around these functions, so the core runs and is testable without any cloud project.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta

from app.allocator import HarvestLot, HouseholdOrder, PartnerOrder, allocate
from app.crops import Crop, crop_from_dict
from app.forecast import ForecastPoint, Series, Signal, forecast
from app.planner import Batch, WeekDemand, plan_line, week_start
from app.store import Store

HORIZON_WEEKS = 14  # long enough to reach a sowable week for the slowest crop (sawi ≈ 11 frozen)


def today(store: Store) -> date:
    return date.fromisoformat(store.meta()["today"])


def crops(store: Store) -> dict[str, Crop]:
    return {d["id"]: crop_from_dict(d) for d in store.list("crops")}


def signals(store: Store) -> list[Signal]:
    out = []
    for s in store.list("signals"):
        if not s.get("accepted"):
            continue
        week_to = s.get("week_to") or (date.fromisoformat(s["week_from"]) + timedelta(weeks=26)).isoformat()
        out.append(Signal(s["id"], s["scope"], s["effect_pct"], date.fromisoformat(s["week_from"]),
                          date.fromisoformat(week_to), s["source"], s["cause"], s.get("crop")))
    return out


def recent_avg_kg(store: Store, weeks: int = 4) -> dict[str, float]:
    """Last-N-week average kg per partner×crop and households×crop, so a note in kg becomes a %."""
    out: dict[str, float] = defaultdict(float)
    for s, hist in history(store).items():
        who = s.partner_id or "households"
        out[f"{who}/{s.crop}"] += sum(kg for _, kg in hist[-weeks:]) / weeks
    return {k: round(v, 1) for k, v in sorted(out.items())}


def history(store: Store) -> dict[Series, list[tuple[date, float]]]:
    """Weekly kg per series; weeks without orders count as 0 (a partner that skipped a week)."""
    meta = store.meta()
    first = date.fromisoformat(meta["first_week"])
    weeks = [first + timedelta(weeks=i) for i in range(meta["weeks"])]
    kg: dict[Series, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for o in store.list("orders"):
        s = Series(o["crop"], o["line"], o["channel"], o.get("partner_id") if o["channel"] == "B2B" else None)
        kg[s][date.fromisoformat(o["week"])] += o["kg"]
    return {s: [(w, round(by_week.get(w, 0.0), 2)) for w in weeks] for s, by_week in kg.items()}


def run_forecast(store: Store, horizon: int = HORIZON_WEEKS) -> dict[Series, list[ForecastPoint]]:
    start = week_start(today(store))
    sigs = signals(store)
    return {s: forecast(h, s, start, horizon, sigs) for s, h in history(store).items()}


def series_key(s: Series) -> str:
    return "/".join(p for p in (s.crop, s.line, s.channel, s.partner_id) if p)


def forecast_view(store: Store, horizon: int = HORIZON_WEEKS) -> list[dict]:
    hist = history(store)
    return [{"series": asdict(s), "key": series_key(s), "history": [{"week": w, "kg": kg} for w, kg in hist[s]],
             "forecast": [asdict(p) for p in pts]}
            for s, pts in sorted(run_forecast(store, horizon).items(), key=lambda kv: series_key(kv[0]))]


def _batches(store: Store) -> list[Batch]:
    return [Batch(b["id"], b["crop"], b["line"], b["farmer_id"], b["beds"], date.fromisoformat(b["seeded_on"]),
                  date.fromisoformat(b["transplanted_on"]), b.get("status", "bed"), b.get("loss_pct", 0.0),
                  date.fromisoformat(b["harvest_on"]) if b.get("harvest_on") else None)
            for b in store.list("batches")]


def run_plan(store: Store, horizon: int = HORIZON_WEEKS) -> list[dict]:
    fc = run_forecast(store, horizon)
    batches = _batches(store)
    farmers = store.list("farmers")
    plans = []
    for crop in crops(store).values():
        capacity = {f["id"]: f["beds"][crop.id] for f in farmers if crop.id in f.get("beds", {})}
        for ln in crop.demand_lines:
            # Partners' downsides are independent: add their band half-widths in quadrature,
            # not linearly (that would assume every partner has a bad week at once).
            expected: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
            var: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
            for s, pts in fc.items():
                if s.crop != crop.id or s.line != ln.id:
                    continue
                for p in pts:
                    expected[p.week][s.channel] += p.expected
                    var[p.week][s.channel] += (p.expected - p.low) ** 2
            low = {w: {ch: max(0.0, e - math.sqrt(var[w][ch])) for ch, e in d.items()} for w, d in expected.items()}
            demand = [WeekDemand(w, d["B2B"], d["B2C"], low[w].get("B2B", 0.0), low[w].get("B2C", 0.0))
                      for w, d in expected.items()]
            plan = plan_line(crop, ln.id, today(store), demand, batches, capacity)
            plans.append(asdict(plan))
    return plans


def run_scenario(store: Store, crop_id: str, week: date, harvest_pct: float) -> dict:
    """What happens if only `harvest_pct` of the expected harvest of `week` comes in."""
    crop = crops(store)[crop_id]
    wk = week_start(week)
    lots = []
    for b in _batches(store):
        if b.crop != crop_id or week_start(b.planned_harvest(crop)) != wk:
            continue
        bed_day = (b.planned_harvest(crop) - b.transplanted_on).days
        lots.append(HarvestLot(b.line, b.expected_kg(crop) * harvest_pct / 100, bed_day))

    partners = {p["id"]: p for p in store.list("partners")}
    p_orders = []
    for s, pts in run_forecast(store).items():
        if s.crop != crop_id or s.channel != "B2B":
            continue
        pt = next((p for p in pts if p.week == wk), None)
        if pt:
            corridor = partners[s.partner_id]["corridor"].get(f"{s.crop}/{s.line}", {})
            p_orders.append(PartnerOrder(s.partner_id, s.line, round(pt.expected, 1), corridor.get("min_kg", 0.0)))

    h_orders = []
    for h in store.list("households"):
        last = max((date.fromisoformat(w) for w in h.get("shortfall_weeks", [])), default=None)
        for key, kg in h["basket"].items():
            c, line = key.split("/")
            if c == crop_id:
                h_orders.append(HouseholdOrder(h["id"], line, kg, last))

    a = allocate(crop, wk, lots, p_orders, h_orders)
    return {**asdict(a), "harvest_pct": harvest_pct, "harvested_kg": round(sum(lt.kg for lt in lots), 1),
            "served_pct": a.served_pct, "preference_miss_kg": a.preference_miss_kg,
            "shorted_households": a.shorted_households}
