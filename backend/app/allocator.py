"""Harvest scenario → allocation for one crop in one week.

The harvest day decides the zone of each lot, which sets its grade split and which channels its
size fits. Allocation order:
1. Each line serves its own orders: B2B from grade B, then A; B2C from grade A. Only when the
   lot's zone fits that channel.
2. Cross-fill (an adjustment, never planned): a line still short takes spare kg from another line
   of the same crop whose zone fits the channel. Logged with a reason; counted as a preference miss
   because the customer gets a different size than they asked for.
3. What is still short is rationed: B2B partners get their agreed minimums first, the rest
   pro-rata; B2C households are shorted in rotation — whoever was shorted least recently goes first,
   and nobody two weeks in a row when it can be avoided.
4. Leftover A/B → surplus; grade C and anything out of every zone → waste.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.crops import Crop

B2B_GRADES = ("B", "A")
B2C_GRADES = ("A",)


@dataclass(frozen=True)
class HarvestLot:
    line: str
    kg: float  # actual harvested kg (all grades)
    bed_day: int


@dataclass(frozen=True)
class PartnerOrder:
    partner_id: str
    line: str
    kg: float
    min_kg: float = 0.0


@dataclass(frozen=True)
class HouseholdOrder:
    household_id: str
    line: str
    kg: float
    last_shorted: date | None = None


@dataclass
class Served:
    customer_id: str
    line: str
    ordered_kg: float
    served_kg: float = 0.0

    @property
    def short_kg(self) -> float:
        return round(self.ordered_kg - self.served_kg, 3)


@dataclass(frozen=True)
class CrossFill:
    from_line: str
    to_line: str
    channel: str
    kg: float
    reason: str


@dataclass
class Allocation:
    crop: str
    week: date
    partners: list[Served]
    households: list[Served]
    cross_fills: list[CrossFill] = field(default_factory=list)
    surplus_kg: float = 0.0
    waste_kg: float = 0.0

    @property
    def preference_miss_kg(self) -> float:
        return round(sum(c.kg for c in self.cross_fills), 2)

    @property
    def shorted_households(self) -> list[str]:
        return [h.customer_id for h in self.households if h.short_kg > 0]

    @property
    def served_pct(self) -> float:
        rows = self.partners + self.households
        ordered = sum(r.ordered_kg for r in rows)
        return round(100 * sum(r.served_kg for r in rows) / ordered, 1) if ordered else 100.0


class _Pools:
    """Remaining kg per line, per grade, plus which channels each line's harvest fits."""

    def __init__(self, crop: Crop, lots: list[HarvestLot]):
        self.kg: dict[str, dict[str, float]] = {}
        self.fits: dict[str, set[str]] = {}
        self.waste = 0.0
        for lot in lots:
            z = crop.zone_at(lot.bed_day)
            if z is None:
                self.waste += lot.kg
                continue
            pool = self.kg.setdefault(lot.line, {"A": 0.0, "B": 0.0, "C": 0.0})
            for g, share in z.grade_share.items():
                pool[g] += lot.kg * share
            self.fits.setdefault(lot.line, set()).update(z.fits)

    def take(self, line: str, channel: str, kg: float) -> float:
        if kg <= 0 or channel not in self.fits.get(line, set()):
            return 0.0
        got = 0.0
        for g in B2B_GRADES if channel == "B2B" else B2C_GRADES:
            t = min(self.kg[line][g], kg - got)
            self.kg[line][g] -= t
            got += t
        return got


def _ration_partners(rows: list[Served], mins: dict[str, float], supply: float) -> None:
    total_min = sum(min(mins[r.customer_id], r.ordered_kg) for r in rows)
    if supply <= total_min:
        for r in rows:
            m = min(mins[r.customer_id], r.ordered_kg)
            r.served_kg = round(supply * m / total_min, 2) if total_min else 0.0
        return
    rest = supply - total_min
    above = sum(r.ordered_kg - min(mins[r.customer_id], r.ordered_kg) for r in rows)
    for r in rows:
        m = min(mins[r.customer_id], r.ordered_kg)
        r.served_kg = round(m + (rest * (r.ordered_kg - m) / above if above else 0), 2)


def _ration_households(rows: list[Served], orders: list[HouseholdOrder], supply: float, week: date) -> None:
    """Cut whole households in rotation order until the rest can be served."""
    last = {o.household_id: o.last_shorted for o in orders}
    shorted_last_week = lambda hid: last[hid] is not None and 0 < (week - last[hid]).days <= 7  # noqa: E731
    # Shorted first: not shorted last week, then whoever was shorted longest ago (never = longest).
    order = sorted(rows, key=lambda r: (shorted_last_week(r.customer_id), last[r.customer_id] or date.min,
                                        r.customer_id))
    deficit = sum(r.ordered_kg for r in rows) - supply
    for r in rows:
        r.served_kg = r.ordered_kg
    for r in order:
        if deficit <= 1e-9:
            break
        cut = min(r.ordered_kg, deficit)
        r.served_kg = round(r.ordered_kg - cut, 2)
        deficit -= cut


def allocate(crop: Crop, week: date, lots: list[HarvestLot], partners: list[PartnerOrder],
             households: list[HouseholdOrder]) -> Allocation:
    pools = _Pools(crop, lots)
    lines = [ln.id for ln in crop.demand_lines]
    p_rows = [Served(o.partner_id, o.line, o.kg) for o in partners]
    h_rows = [Served(o.household_id, o.line, o.kg) for o in households]
    mins = {o.partner_id: o.min_kg for o in partners}

    def demand(channel: str, line: str) -> float:
        rows = p_rows if channel == "B2B" else h_rows
        return sum(r.ordered_kg for r in rows if r.line == line)

    # 1. own line, B2B first (contracts), then B2C
    supply: dict[tuple[str, str], float] = {}
    for ch in ("B2B", "B2C"):
        for ln in lines:
            supply[ch, ln] = pools.take(ln, ch, demand(ch, ln))

    # 2. cross-fill between lines of this crop (adjustment only)
    fills = []
    for ch in ("B2B", "B2C"):
        for ln in lines:
            short = demand(ch, ln) - supply[ch, ln]
            for other in lines:
                if short <= 1e-9 or other == ln:
                    continue
                got = pools.take(other, ch, short)
                if got > 0:
                    supply[ch, ln] += got
                    short -= got
                    fills.append(CrossFill(other, ln, ch, round(got, 2),
                                           f"{ln} short for {ch}; {other} harvest fits {ch} (size differs)"))

    # 3. ration what is still short
    for ln in lines:
        rows = [r for r in p_rows if r.line == ln]
        if rows:
            _ration_partners(rows, mins, supply["B2B", ln])
        rows = [r for r in h_rows if r.line == ln]
        if rows:
            _ration_households(rows, [o for o in households if o.line == ln], supply["B2C", ln], week)

    # 4. leftovers
    surplus = sum(p["A"] + p["B"] for p in pools.kg.values())
    waste = pools.waste + sum(p["C"] for p in pools.kg.values())
    return Allocation(crop.id, week, p_rows, h_rows, fills, round(surplus, 2), round(waste, 2))
