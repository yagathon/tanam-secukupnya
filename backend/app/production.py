"""Batches in the beds: what each holds on a day, what a harvest sample says, and the day-by-day
projection every engine output runs on. Pure; no I/O.

Readiness is cumulative: we always harvest the biggest in-range plants first, so
waste_cum = max(0, plants0·F_over − harvested − lost) and
available = max(0, plants0·F_ready − harvested − waste_cum − lost).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import date, timedelta
from functools import lru_cache

from app.growth import Crop, curve, in_range_mean, share_from

SIZE_MIN, SIZE_MAX = 0.5, 1.5


@dataclass
class Batch:
    id: str
    label: str
    line: str
    sown_on: date
    seedlings: int
    size_factor: float = 1.0           # this bed's plants vs the reference curve (model B: stunting, crowding)
    spread_ratio: float | None = None  # None → the crop's prior
    harvested_plants: float = 0.0
    lost_plants: float = 0.0
    sampled: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Batch":
        names = {f.name for f in fields(cls)}
        row = {k: v for k, v in d.items() if k in names}
        if isinstance(row["sown_on"], str):
            row["sown_on"] = date.fromisoformat(row["sown_on"])
        return cls(**row)

    def to_dict(self) -> dict:
        return {**asdict(self), "sown_on": self.sown_on.isoformat()}


def plants0(crop: Crop, b: Batch) -> float:
    return b.seedlings * crop.survival


def spread(crop: Crop, b: Batch) -> float:
    return crop.spread_ratio if b.spread_ratio is None else b.spread_ratio


def bed_day(crop: Crop, b: Batch, d: date) -> int:
    return (d - b.sown_on).days - crop.nursery_days


def avg_g(crop: Crop, b: Batch, d: date) -> float:
    return b.size_factor * curve(crop, bed_day(crop, b, d))


@lru_cache(maxsize=262144)
def _at(crop: Crop, line_id: str, bd: int, size: float, r: float) -> tuple[float, float, float]:
    """(F_ready, F_over, kg per harvested plant) for one bed day. Cached: projections ask this a lot."""
    if bd < 0:
        return 0.0, 0.0, 0.0
    line = crop.line(line_id)
    avg = size * curve(crop, bd)
    over = 1.0 if bd > crop.max_bed_day else share_from(avg, r, line.top_g)
    return share_from(avg, r, line.min_g), over, in_range_mean(avg, r, line) / 1000


def shares(crop: Crop, b: Batch, d: date) -> tuple[float, float]:
    """(F_ready, F_over): share at/above the line's minimum, and past what it can still send (top_g) (all of it after max_bed_day)."""
    ready, over, _ = _at(crop, b.line, bed_day(crop, b, d), b.size_factor, spread(crop, b))
    return ready, over


def waste_plants(crop: Crop, b: Batch, d: date) -> float:
    _, over = shares(crop, b, d)
    return max(0.0, plants0(crop, b) * over - b.harvested_plants - b.lost_plants)


def available_plants(crop: Crop, b: Batch, d: date) -> float:
    ready, over = shares(crop, b, d)
    p0, gone = plants0(crop, b), b.harvested_plants + b.lost_plants
    return max(0.0, p0 * ready - gone - max(0.0, p0 * over - gone))


def in_bed_plants(crop: Crop, b: Batch, d: date) -> float:
    return max(0.0, plants0(crop, b) - b.harvested_plants - b.lost_plants - waste_plants(crop, b, d))


def kg_per_plant(crop: Crop, b: Batch, d: date) -> float:
    kpp = _at(crop, b.line, bed_day(crop, b, d), b.size_factor, spread(crop, b))[2]
    return kpp or crop.line(b.line).min_g / 1000


def available_kg(crop: Crop, b: Batch, d: date) -> float:
    return available_plants(crop, b, d) * kg_per_plant(crop, b, d)


def harvest(crop: Crop, b: Batch, d: date, kg: float, grams_each: float | None = None) -> Batch:
    g = grams_each or kg_per_plant(crop, b, d) * 1000
    return replace(b, harvested_plants=b.harvested_plants + kg * 1000 / g)


def apply_sample(crop: Crop, b: Batch, d: date, kg: float, big5_g: float, small5_g: float) -> Batch:
    """The 5 biggest and 5 smallest weighed together → average, size factor, spread, plants picked."""
    if not big5_g >= small5_g > 0:
        raise ValueError("a harvest sample needs big5 ≥ small5 > 0")
    big, small = big5_g / 5, small5_g / 5
    avg = (big + small) / 2
    size = min(SIZE_MAX, max(SIZE_MIN, avg / curve(crop, bed_day(crop, b, d))))
    b = replace(b, size_factor=round(size, 3), spread_ratio=round((big - small) / avg, 3), sampled=True)
    return harvest(crop, b, d, kg, grams_each=avg)


def apply_loss(crop: Crop, b: Batch, d: date, pct: float) -> Batch:
    pct = max(0.0, min(100.0, pct))
    return replace(b, lost_plants=b.lost_plants + pct / 100 * in_bed_plants(crop, b, d))


def take_oldest(crop: Crop, batches: list[Batch], d: date, kg: float) -> list[tuple[Batch, float]]:
    """Harvest up to `kg` on day d, oldest batch first. Mutates the given batches; returns (batch, kg) taken."""
    taken = []
    got = 0.0
    for b in sorted(batches, key=lambda b: (b.sown_on, b.id)):
        if kg - got <= 1e-9:
            break
        kpp = kg_per_plant(crop, b, d)
        t = min(available_plants(crop, b, d) * kpp, kg - got)
        if t > 1e-9:
            b.harvested_plants += t / kpp
            got += t
            taken.append((b, t))
    return taken


@dataclass
class DayProj:
    day: date
    need_kg: float
    available_kg: float
    harvested_kg: float
    short_kg: float
    waste_plants: float


def project(crop: Crop, line: str, batches: list[Batch], need: dict[date, float], start: date, end: date,
            send: dict[date, float] | None = None) -> list[DayProj]:
    """Day by day from start to end: serve each day's need (or `send[d]`, when given) oldest batch first."""
    bs = [replace(b) for b in batches if b.line == line]
    send = send or {}
    out: list[DayProj] = []
    wasted = sum(waste_plants(crop, b, start - timedelta(days=1)) for b in bs)
    d = start
    while d <= end:
        n = need.get(d, 0.0)
        avail = sum(available_kg(crop, b, d) for b in bs)
        got = sum(t for _, t in take_oldest(crop, bs, d, send.get(d, n)))
        w = sum(waste_plants(crop, b, d) for b in bs)
        out.append(DayProj(d, n, avail, got, max(0.0, n - got), max(0.0, w - wasted)))
        wasted = max(wasted, w)
        d += timedelta(days=1)
    return out
