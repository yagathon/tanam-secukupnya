"""The daily engine: needs per day, max safe to send tomorrow, who is served, and what to sow next.

Everything runs on production.project (one deterministic day-by-day projection per line).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from app import demand
from app.growth import Crop, first_ready_day, seeds_for
from app.production import Batch, available_kg, project

SOW_WEEKDAYS = (0, 3)  # Mon, Thu (D4)
SEEDLING_STEP = 50
EPS_KG = 0.05


def b2b_key(buyer: str, line: str) -> str:
    return f"b2b:{buyer}:{line}"


def hh_key(line: str) -> str:
    return f"hh:{line}"


def signal_factor(signals: list[dict], key: str, d: date) -> float:
    """Accepted demand signals: scope all | channel:B2B | channel:B2C | buyer:<id>; line None = every line."""
    kind, *rest = key.split(":")
    f = 1.0
    for s in signals:
        if not (s["date_from"] <= d.isoformat() <= s["date_to"]):
            continue
        if s.get("line") and s["line"] != rest[-1]:
            continue
        sc = s["scope"]
        hit = (sc == "all" or (sc == "channel:B2B" and kind == "b2b") or (sc == "channel:B2C" and kind == "hh")
               or (kind == "b2b" and sc == f"buyer:{rest[0]}"))
        if hit:
            f *= max(0.0, 1 + s["effect_pct"] / 100)
    return f


@dataclass
class LineNeeds:
    line: str
    tomorrow: float
    tomorrow_parts: dict[str, float]          # series key → kg (known order or expected)
    known: dict[str, float]                   # buyer → tomorrow's known order kg
    protected: dict[date, float]
    target: dict[date, float]
    rows: list[dict] = field(default_factory=list)  # per day: low/expected/high for the Demand tab


def series_for(line: str, buyers: list[dict]) -> list[str]:
    return [b2b_key(b["id"], line) for b in buyers if line in b["lines"]] + [hh_key(line)]


def line_needs(model: demand.DemandModel, buyers: list[dict], line: str, today: date, end: date,
               known_orders: dict[tuple[str, str, str], float], signals: list[dict]) -> LineNeeds:
    """known_orders: (iso day, buyer, line) → kg."""
    tom = today + timedelta(days=1)
    keys = [k for k in series_for(line, buyers) if k in model.fits]
    parts, known = {}, {}
    for k in keys:
        f = signal_factor(signals, k, tom)
        if k.startswith("b2b:"):
            buyer = k.split(":")[1]
            if (tom.isoformat(), buyer, line) in known_orders:
                known[buyer] = parts[k] = known_orders[tom.isoformat(), buyer, line]
                continue
        parts[k] = demand.expected(model, k, tom, f)
    protected, target, rows = {}, {}, []
    d = tom
    while d <= end:
        h = (d - today).days
        e_all = hi_all = lo_all = b2b_e = b2b_hi = 0.0
        hh_lo = hh_hi = 0.0
        for k in keys:
            lo, e, hi = demand.band(model, k, d, h, signal_factor(signals, k, d))
            e_all, lo_all, hi_all = e_all + e, lo_all + lo, hi_all + hi
            if k.startswith("b2b:"):
                b2b_e, b2b_hi = b2b_e + e, b2b_hi + hi
            else:
                hh_lo, hh_hi = hh_lo + lo, hh_hi + hi
        protected[d] = b2b_e + hh_lo
        target[d] = b2b_hi + hh_hi
        rows.append({"day": d.isoformat(), "low": round(lo_all, 2), "expected": round(e_all, 2),
                     "high": round(hi_all, 2), "protected": round(protected[d], 2), "target": round(target[d], 2)})
        d += timedelta(days=1)
    protected[tom] = sum(parts.values())
    return LineNeeds(line, sum(parts.values()), parts, known, protected, target, rows)


def next_sow_day(today: date, sown_today: bool) -> date:
    d = today + timedelta(days=1 if sown_today else 0)
    while d.weekday() not in SOW_WEEKDAYS:
        d += timedelta(days=1)
    return d


def horizon_end(crop: Crop, line: str, today: date, sown_today: bool) -> date:
    """(b)'s horizon: through the first ready day of the next sowing's batch."""
    return first_ready_day(crop, crop.line(line), next_sow_day(today, sown_today))


def _future_short(crop, line, batches, need, tom, end, x) -> float:
    proj = project(crop, line, batches, need, tom, end, send={tom: x})
    return sum(p.short_kg for p in proj[1:])


def _floor2(x: float) -> float:
    """Round down to 10 g: rounding up could step past the safe point."""
    return math.floor(x * 100) / 100


def ceiling(crop: Crop, line: str, batches: list[Batch], need: dict[date, float], today: date, end: date) -> float:
    """Largest tomorrow harvest x ≤ available(tomorrow) that leaves the projected shortfall after tomorrow
    no worse than harvesting nothing."""
    tom = today + timedelta(days=1)
    avail = sum(available_kg(crop, b, tom) for b in batches if b.line == line)
    base = _future_short(crop, line, batches, need, tom, end, 0.0)
    if _future_short(crop, line, batches, need, tom, end, avail) <= base + EPS_KG:
        return _floor2(avail)
    lo, hi = 0.0, avail
    for _ in range(30):
        mid = (lo + hi) / 2
        if _future_short(crop, line, batches, need, tom, end, mid) <= base + EPS_KG:
            lo = mid
        else:
            hi = mid
    return _floor2(lo)


def borrowing(crop: Crop, line: str, batches: list[Batch], need: dict[date, float], today: date, end: date,
              x: float, ceil: float) -> list[dict]:
    """Sending x > ceiling: the later days whose shortfall grows, and by how much."""
    tom = today + timedelta(days=1)
    a = project(crop, line, batches, need, tom, end, send={tom: ceil})
    b = project(crop, line, batches, need, tom, end, send={tom: x})
    return [{"day": pb.day.isoformat(), "kg": round(pb.short_kg - pa.short_kg, 2)}
            for pa, pb in zip(a[1:], b[1:]) if pb.short_kg - pa.short_kg > EPS_KG]


@dataclass
class SowPlan:
    line: str
    day: date
    seedlings: int
    seeds_g: float
    teaspoons: float
    ready_from: date
    covers_until: date
    gap_kg: float
    capped: bool
    shortfall_ahead: list[dict]


def missed_slots(last_sown: date | None, day: date) -> list[date]:
    """Mon/Thu sowing days strictly between the last real sowing and `day` (they have no batch)."""
    if last_sown is None:
        return []
    out, d = [], last_sown + timedelta(days=1)
    while d < day:
        if d.weekday() in SOW_WEEKDAYS:
            out.append(d)
        d += timedelta(days=1)
    return out


def sow_next(crop: Crop, line: str, batches: list[Batch], protected: dict[date, float], target: dict[date, float],
             today: date, last_sown: date | None, sown_today: bool) -> SowPlan:
    """Smallest seedling count (step 50, ≤ the crop cap) that makes every coverage day the new batch can
    reach shortfall-free against the sowing target. Coverage: its first ready day until the following
    sowing's first ready day. Earlier days left uncovered by missed sowings are shortfall ahead."""
    ln = crop.line(line)
    day = next_sow_day(today, sown_today)
    following = next_sow_day(day + timedelta(days=1), False)
    start = first_ready_day(crop, ln, day)
    end = first_ready_day(crop, ln, following) - timedelta(days=1)
    # Size as if the following sowing gets the same count, over both windows: a batch's tail runs into
    # the next window, so sizing one window alone makes sowings swing big/small/big.
    end2 = first_ready_day(crop, ln, next_sow_day(following + timedelta(days=1), False)) - timedelta(days=1)
    missed = missed_slots(last_sown, day)
    cov_start = min([first_ready_day(crop, ln, m) for m in missed] + [start])
    tom = today + timedelta(days=1)
    need = {d: (target.get(d, 0.0) if d >= cov_start else protected.get(d, 0.0))
            for d in (tom + timedelta(days=i) for i in range((end2 - tom).days + 1))}

    def short_with(n: int) -> list:
        new = [Batch(id="_new", label="new", line=line, sown_on=day, seedlings=n),
               Batch(id="_next", label="next", line=line, sown_on=following, seedlings=n)]
        return project(crop, line, [*batches, *new] if n else list(batches), need, tom, end2)

    def gap(n: int) -> float:
        return sum(p.short_kg for p in short_with(n) if p.day >= start)

    cap = crop.max_seedlings
    if gap(cap) > EPS_KG:
        n, capped = cap, True
    else:
        lo, hi = 0, cap // SEEDLING_STEP
        while lo < hi:
            mid = (lo + hi) // 2
            if gap(mid * SEEDLING_STEP) <= EPS_KG:
                hi = mid
            else:
                lo = mid + 1
        n, capped = lo * SEEDLING_STEP, False
    proj = short_with(n)
    ahead = [{"day": p.day.isoformat(), "kg": round(p.short_kg, 2)} for p in proj
             if p.short_kg > EPS_KG and (p.day < start or capped)]
    g, tsp = seeds_for(crop, n)
    return SowPlan(line, day, n, g, tsp, start, end, round(gap(0), 2), capped, ahead)
