"""The hidden truth world: real daily demand, real growth per batch, rain and pests.

Deterministic from a seed, so every visitor (and the video) sees the same world. SYNTHETIC (D10:
aliases only). The engine never reads this module; only the day loop (sim.py) and the generator do.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

from app.growth import Crop

SEED = 20261014
DAY0 = date(2026, 10, 12)          # demo "today", a Monday
HISTORY_DAYS = 56                  # 8 weeks of order history before DAY0
FUTURE_DAYS = 182                  # 26 weeks ahead
WARMUP_DAYS = 100                  # the farm runs this long before DAY0 so the beds are full on DAY0
START = DAY0 - timedelta(days=WARMUP_DAYS)
MARKET_DROP_FROM = DAY0 + timedelta(days=7)   # week 10 of the 8 + 26-week world
MARKET_DROP = 0.85
RAIN_DAYS = (DAY0 + timedelta(days=10), DAY0 + timedelta(days=73))   # two Thursdays
PEST = (DAY0 + timedelta(days=20), "regular", 30.0, "caterpillars")  # day, line, % of the oldest bed, cause

BUYERS = [
    {"id": "resto_a", "alias": "Restaurant A", "segment": "restaurant", "weekdays": [0, 1, 2, 3, 4, 5],
     "lines": {"regular": {"kg": 7.0, "min_kg": 3.0}}, "peak": {4: 1.2, 5: 1.3}, "trend_per_week": -0.03},
    {"id": "resto_b", "alias": "Restaurant B", "segment": "restaurant", "weekdays": [0, 1, 2, 3, 4, 5],
     "lines": {"regular": {"kg": 9.0, "min_kg": 4.0}}, "peak": {5: 1.25}, "trend_per_week": 0.0},
    {"id": "caterer_c", "alias": "Caterer C (school meals)", "segment": "school_caterer", "weekdays": [0, 1, 2, 3, 4],
     "lines": {"regular": {"kg": 12.0, "min_kg": 6.0}}, "peak": {}, "trend_per_week": 0.0},
    {"id": "hotel_d", "alias": "Hotel D", "segment": "hotel", "weekdays": [0, 1, 2, 3, 4, 5, 6],
     "lines": {"regular": {"kg": 5.0, "min_kg": 2.0}}, "peak": {5: 1.3, 6: 1.3}, "trend_per_week": 0.0},
    {"id": "warung_e", "alias": "Warung E", "segment": "warung", "weekdays": [0, 2, 4],
     "lines": {"regular": {"kg": 4.0, "min_kg": 0.0}}, "peak": {}, "trend_per_week": 0.0},
]
HH_PAIRS = ([0, 3], [1, 4], [2, 5])  # each household orders on two fixed weekdays


def households() -> list[dict]:
    out = []
    for i in range(30):
        line = "regular" if i < 18 else "baby"
        out.append({"id": f"hh_{i + 1:02d}", "alias": f"Household {i + 1:02d}", "line": line,
                    "kg": 0.5, "weekdays": HH_PAIRS[i % 3]})
    return out


@dataclass(frozen=True)
class World:
    seed: int
    buyers: tuple[dict, ...]
    households: tuple[dict, ...]
    b2b: dict      # (iso day, buyer, line) → kg ordered
    hh: dict       # iso day → [(household, line, kg)]

    def series_actual(self, key: str, d: date) -> float | None:
        kind, *rest = key.split(":")
        if kind == "b2b":
            return self.b2b.get((d.isoformat(), rest[0], rest[1]))
        return round(sum(kg for _, ln, kg in self.hh.get(d.isoformat(), []) if ln == rest[0]), 2)

    def growth_truth(self, crop: Crop, line: str, sown_on: date) -> tuple[float, float]:
        """(size factor vs the reference curve, spread ratio) the batch really has. Independent of the sowing order."""
        r = random.Random(f"{self.seed}:{line}:{sown_on.isoformat()}")
        return round(r.uniform(0.85, 1.15), 3), round(crop.spread_ratio * r.uniform(0.85, 1.15), 3)


def market(d: date) -> float:
    return MARKET_DROP if d >= MARKET_DROP_FROM else 1.0


@lru_cache(maxsize=8)
def build(seed: int = SEED) -> World:
    rng = random.Random(seed)
    b2b, hh = {}, {}
    hhs = households()
    for i in range(WARMUP_DAYS + FUTURE_DAYS + 3):
        d = START + timedelta(days=i)
        weeks = (d - DAY0).days / 7
        for b in BUYERS:
            if d.weekday() not in b["weekdays"]:
                continue
            for line, spec in b["lines"].items():
                mean = spec["kg"] * b["peak"].get(d.weekday(), 1.0) * (1 + b["trend_per_week"]) ** weeks * market(d)
                b2b[d.isoformat(), b["id"], line] = round(max(0.0, mean * rng.gauss(1, 0.1)), 1)
        rows = []
        for h in hhs:
            if d.weekday() in h["weekdays"] and rng.random() > 0.1:
                rows.append((h["id"], h["line"], round(h["kg"] * market(d) * rng.uniform(0.8, 1.2), 2)))
        hh[d.isoformat()] = rows
    return World(seed, tuple(BUYERS), tuple(hhs), b2b, hh)
