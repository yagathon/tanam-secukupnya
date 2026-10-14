"""Crop growth: grams per plant by bed day, and how a bed's size spread meets a demand line's range.

Pure functions over the crop table (data/seed/crops.json; synthetic values, disclosed). Plant weights
in a bed are modelled as uniform on [avg·(1 − r/2), avg·(1 + r/2)], r = the spread ratio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

READY_SHARE = 0.25  # a batch counts as "ready" for its line once a quarter of its plants are in range


@dataclass(frozen=True)
class Line:
    id: str
    min_g: float
    max_g: float
    channels: tuple[str, ...]


@dataclass(frozen=True, eq=False)  # hashed by identity: production caches lookups per crop object
class Crop:
    id: str
    name: str
    nursery_days: int
    curve: tuple[tuple[float, float], ...]
    spread_ratio: float
    germination: float
    survival: float
    seeds_per_gram: float
    grams_per_teaspoon: float
    max_bed_day: int
    max_seedlings: int
    lines: tuple[Line, ...]

    def line(self, line_id: str) -> Line:
        for ln in self.lines:
            if ln.id == line_id:
                return ln
        raise KeyError(f"{self.id} has no line {line_id!r}")


def crop_from_dict(d: dict) -> Crop:
    pts = tuple((float(x), float(y)) for x, y in d["growth_curve"])
    if len(pts) < 2 or any(b[0] <= a[0] or b[1] <= a[1] for a, b in zip(pts, pts[1:])):
        raise ValueError(f"{d['id']}: growth_curve must be strictly increasing in day and grams")
    return Crop(
        id=d["id"], name=d["name"], nursery_days=int(d["nursery_days"]), curve=pts,
        spread_ratio=float(d["spread_ratio"]), germination=float(d["germination"]), survival=float(d["survival"]),
        seeds_per_gram=float(d["seeds_per_gram"]), grams_per_teaspoon=float(d["grams_per_teaspoon"]),
        max_bed_day=int(d["max_bed_day"]), max_seedlings=int(d.get("max_seedlings_per_sowing", 3000)),
        lines=tuple(Line(ln["id"], float(ln["min_g"]), float(ln["max_g"]), tuple(ln["channels"])) for ln in d["lines"]),
    )


def curve(crop: Crop, day: float) -> float:
    """Grams per plant on an (effective) bed day: piecewise-linear, flat before the first point, the
    last segment's slope continued after the table ends."""
    pts = crop.curve
    if day <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if day <= x1:
            return y0 + (y1 - y0) * (day - x0) / (x1 - x0)
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    return y1 + (y1 - y0) * (day - x1) / (x1 - x0)


def curve_inv(crop: Crop, grams: float) -> float:
    """The bed day on which the average plant weighs `grams`, clamped to the table's day range."""
    pts = crop.curve
    if grams <= pts[0][1]:
        return pts[0][0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if grams <= y1:
            return x0 + (x1 - x0) * (grams - y0) / (y1 - y0)
    return pts[-1][0]


def size_range(avg: float, spread: float) -> tuple[float, float]:
    return avg * (1 - spread / 2), avg * (1 + spread / 2)


def share_from(avg: float, spread: float, grams: float) -> float:
    """Share of plants weighing at least `grams`."""
    lo, hi = size_range(avg, spread)
    if hi - lo < 1e-9:
        return 1.0 if avg >= grams else 0.0
    return min(1.0, max(0.0, (hi - grams) / (hi - lo)))


def in_range_mean(avg: float, spread: float, line: Line) -> float:
    """Mean weight of the plants inside the line's range (the nearest edge when none are)."""
    lo, hi = size_range(avg, spread)
    a, b = max(lo, line.min_g), min(hi, line.max_g)
    if b < a:
        return min(max(avg, line.min_g), line.max_g)
    return (a + b) / 2


def first_ready_day(crop: Crop, line: Line, sown_on: date, offset: float = 0.0, spread: float | None = None) -> date:
    """First day a quarter of the batch's plants are in the line's range."""
    r = crop.spread_ratio if spread is None else spread
    for bd in range(crop.max_bed_day + 1):
        if share_from(curve(crop, bd + offset), r, line.min_g) >= READY_SHARE:
            return sown_on + timedelta(days=crop.nursery_days + bd)
    return sown_on + timedelta(days=crop.nursery_days + crop.max_bed_day)


def seeds_for(crop: Crop, seedlings: int) -> tuple[float, float]:
    """(grams of seed, teaspoons) to raise `seedlings` seedlings."""
    g = seedlings / crop.germination / crop.seeds_per_gram
    return round(g, 1), round(g / crop.grams_per_teaspoon, 2)
