"""Generate the synthetic demand history with deliberately planted patterns.

Everything here is SYNTHETIC (decision D2): the shape comes from field experience at a small
Indonesian farm-to-buyer aggregator, the numbers are invented. The patterns we plant are written
to data/seed/planted_patterns.json, so the evaluation can check whether the system finds them.

    uv run --project backend python scripts/generate.py      # deterministic (fixed seed)
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.crops import crop_from_dict  # noqa: E402
from app.planner import HARVEST_WEEKDAY, harvest_needed, split_beds  # noqa: E402

OUT = ROOT / "data" / "seed"
SEED = 20261018
FIRST_WEEK = date(2026, 1, 5)  # a Monday
WEEKS = 40  # through the week of 2026-10-05
TODAY = date(2026, 10, 12)  # the demo's "today": the Monday after the last week of history

# Planted patterns: (id, description, scope, effect, date_from, date_to)
RAMADAN = (date(2026, 2, 18), date(2026, 3, 19))
LEBARAN = (date(2026, 3, 20), date(2026, 3, 27))
SCHOOL_HOLIDAY = (date(2026, 6, 22), date(2026, 7, 12))

FARMERS = [
    {"id": "farmer_a", "alias": "Farmer A, Bogor", "crops": ["pakcoy"], "beds": {"pakcoy": 14}},
    {"id": "farmer_b", "alias": "Farmer B, Bogor", "crops": ["pakcoy", "sawi_putih"],
     "beds": {"pakcoy": 8, "sawi_putih": 10}},
    {"id": "farmer_c", "alias": "Farmer C, Cianjur", "crops": ["sawi_putih"], "beds": {"sawi_putih": 18}},
    {"id": "farmer_d", "alias": "Farmer D, Cianjur", "crops": ["pakcoy"], "beds": {"pakcoy": 10}},
]

# B2B partners: weekly base kg per (crop, line) and the corridor they agreed to.
PARTNERS = [
    {"id": "resto_a", "alias": "Restaurant A", "segment": "restaurant",
     "base": {"pakcoy/regular": 18, "sawi_putih/restaurant": 30}},
    {"id": "resto_b", "alias": "Restaurant B", "segment": "restaurant", "trend_per_week": 0.01,
     "base": {"pakcoy/regular": 12, "sawi_putih/restaurant": 20}},
    {"id": "caterer_c", "alias": "Caterer C (school meals)", "segment": "school_caterer",
     "base": {"pakcoy/regular": 25, "sawi_putih/restaurant": 35}},
    {"id": "cafe_d", "alias": "Cafe D", "segment": "cafe",
     "base": {"pakcoy/regular": 6}},
]
CORRIDOR = (0.7, 1.3)  # min/max as a share of the partner's base

HOUSEHOLDS = 30
# Each household's usual basket: kg per week per (crop, line) when they order.
HOUSEHOLD_BASKETS = [
    {"pakcoy/regular": 0.5},
    {"pakcoy/baby": 0.4},
    {"sawi_putih/retail": 1.0},
    {"pakcoy/regular": 0.5, "sawi_putih/retail": 1.0},
    {"pakcoy/baby": 0.3, "sawi_putih/retail": 0.8},
]
HOUSEHOLD_ORDER_PROB = 0.75
NOISE_SIGMA = 0.12


def overlaps(week: date, span: tuple[date, date]) -> bool:
    return week <= span[1] and week + timedelta(days=6) >= span[0]


def b2b_factor(p: dict, week: date, i: int) -> float:
    f = (1 + p.get("trend_per_week", 0.0)) ** i
    if overlaps(week, LEBARAN):
        f *= 0.5
    elif overlaps(week, RAMADAN):
        f *= 0.75  # lunch trade drops while fasting
    if p["segment"] == "school_caterer" and overlaps(week, SCHOOL_HOLIDAY):
        f *= 0.4
    return f


def b2c_factor(week: date) -> float:
    f = 1.0
    if overlaps(week, LEBARAN):
        f *= 0.7  # families travel home (mudik)
    elif overlaps(week, RAMADAN):
        f *= 1.15  # more home cooking for iftar
    if any((week + timedelta(days=d)).day == 25 for d in range(7)):
        f *= 1.12  # payday week
    return f


# Planted gaps in what's already in the ground, so the demo shows a bridge and a shortfall.
# (crop, line, harvest week) → beds removed, and why.
IN_GROUND_GAPS = {
    ("pakcoy", "regular", date(2026, 10, 26)): (2, "Farmer D's seedlings were transplanted late"),
    ("sawi_putih", "retail", date(2026, 11, 9)): (1, "a nursery tray failed"),
}


def in_ground_batches(orders: list[dict]) -> list[dict]:
    """Batches already sown for every week a new sowing can no longer reach (the frozen weeks).

    Sized to cover the recent average demand of their line, except the planted gaps above.
    """
    crops = [crop_from_dict(d) for d in json.loads((OUT / "crops.json").read_text())]
    recent = {(FIRST_WEEK + timedelta(weeks=i)).isoformat() for i in range(WEEKS - 8, WEEKS)}
    avg: dict[tuple[str, str, str], float] = defaultdict(float)
    for o in orders:
        if o["week"] in recent:
            avg[o["crop"], o["line"], o["channel"]] += o["kg"] / len(recent)
    batches = []
    for crop in crops:
        capacity = {f["id"]: f["beds"][crop.id] for f in FARMERS if crop.id in f["beds"]}
        for ln in crop.demand_lines:
            target = harvest_needed(crop, ln.id, avg[crop.id, ln.id, "B2B"], avg[crop.id, ln.id, "B2C"])
            beds = math.ceil(target / crop.kg_per_bed_for_line(ln.id))
            midpoint = crop.zone(ln.target_zone).midpoint
            week = TODAY - timedelta(days=TODAY.weekday())
            while True:
                harvest_on = week + timedelta(days=HARVEST_WEEKDAY)
                transplanted = harvest_on - timedelta(days=midpoint)
                seeded = transplanted - timedelta(days=crop.nursery_days)
                if seeded >= TODAY:
                    break
                gap, why = IN_GROUND_GAPS.get((crop.id, ln.id, week), (0, None))
                for farmer, b in split_beds(beds - gap, capacity).items():
                    batches.append({
                        "id": f"{crop.id}-{ln.id}-{week.isoformat()}-{farmer}", "crop": crop.id, "line": ln.id,
                        "farmer_id": farmer, "beds": b, "seeded_on": seeded.isoformat(),
                        "transplanted_on": transplanted.isoformat(),
                        "status": "nursery" if transplanted > TODAY else "bed",
                        **({"note": why} if why else {})})
                week += timedelta(weeks=1)
    return batches


def main() -> None:
    rng = random.Random(SEED)
    noise = lambda: rng.lognormvariate(0, NOISE_SIGMA)  # noqa: E731

    partners = []
    for p in PARTNERS:
        corridor = {k: {"min_kg": round(v * CORRIDOR[0], 1), "max_kg": round(v * CORRIDOR[1], 1)}
                    for k, v in p["base"].items()}
        partners.append({"id": p["id"], "alias": p["alias"], "segment": p["segment"], "corridor": corridor})

    households = [{"id": f"hh_{n:02d}", "alias": f"Household {n:02d}",
                   "basket": HOUSEHOLD_BASKETS[n % len(HOUSEHOLD_BASKETS)], "shortfall_weeks": []}
                  for n in range(1, HOUSEHOLDS + 1)]

    orders = []
    for i in range(WEEKS):
        week = FIRST_WEEK + timedelta(weeks=i)
        for p in PARTNERS:
            f = b2b_factor(p, week, i)
            for key, base in p["base"].items():
                crop, line = key.split("/")
                orders.append({"week": week.isoformat(), "channel": "B2B", "partner_id": p["id"],
                               "crop": crop, "line": line, "kg": round(base * f * noise(), 1)})
        f = b2c_factor(week)
        for hh in households:
            if rng.random() > HOUSEHOLD_ORDER_PROB * min(f, 1.3):
                continue
            for key, kg in hh["basket"].items():
                crop, line = key.split("/")
                orders.append({"week": week.isoformat(), "channel": "B2C", "household_id": hh["id"],
                               "crop": crop, "line": line, "kg": round(kg * noise(), 2)})

    patterns = [
        {"id": "ramadan", "scope": "B2B all", "effect_pct": -25, "from": RAMADAN[0].isoformat(),
         "to": RAMADAN[1].isoformat(), "cause": "Ramadan: lunch trade drops while fasting"},
        {"id": "ramadan_b2c", "scope": "B2C all", "effect_pct": 15, "from": RAMADAN[0].isoformat(),
         "to": RAMADAN[1].isoformat(), "cause": "Ramadan: more home cooking for iftar"},
        {"id": "lebaran", "scope": "B2B all", "effect_pct": -50, "from": LEBARAN[0].isoformat(),
         "to": LEBARAN[1].isoformat(), "cause": "Lebaran holiday week"},
        {"id": "lebaran_b2c", "scope": "B2C all", "effect_pct": -30, "from": LEBARAN[0].isoformat(),
         "to": LEBARAN[1].isoformat(), "cause": "Lebaran: families travel home (mudik)"},
        {"id": "school_holiday", "scope": "partner caterer_c", "effect_pct": -60,
         "from": SCHOOL_HOLIDAY[0].isoformat(), "to": SCHOOL_HOLIDAY[1].isoformat(),
         "cause": "School holiday: the school caterer cooks far less"},
        {"id": "payday", "scope": "B2C all", "effect_pct": 12, "from": None, "to": None,
         "cause": "Payday week (the 25th)"},
        {"id": "growth_resto_b", "scope": "partner resto_b", "effect_pct": 1, "from": None, "to": None,
         "cause": "Restaurant B grows ~1% per week"},
    ]

    meta = {"synthetic": True, "seed": SEED, "first_week": FIRST_WEEK.isoformat(), "weeks": WEEKS,
            "today": TODAY.isoformat(), "noise_sigma": NOISE_SIGMA}
    gaps = [{"crop": c, "line": ln, "week": w.isoformat(), "beds_missing": n, "cause": why}
            for (c, ln, w), (n, why) in IN_GROUND_GAPS.items()]
    files = {"farmers.json": FARMERS, "partners.json": partners, "households.json": households,
             "orders.json": orders, "batches.json": in_ground_batches(orders),
             "planted_patterns.json": {"meta": meta, "patterns": patterns, "in_ground_gaps": gaps}}
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (OUT / name).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(orders)} orders over {WEEKS} weeks → {OUT}")


if __name__ == "__main__":
    main()
