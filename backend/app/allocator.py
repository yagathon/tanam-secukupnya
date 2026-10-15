"""Who gets served when one day's harvest is below that day's need.

B2B buyers get their agreed minimums first, the rest pro-rata. Households are cut whole, in
rotation: whoever was shorted least recently goes first, and nobody twice within 7 days when it
can be avoided.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BuyerOrder:
    buyer_id: str
    kg: float
    min_kg: float = 0.0


@dataclass(frozen=True)
class HouseholdOrder:
    household_id: str
    kg: float
    last_shorted: date | None = None


@dataclass
class Served:
    customer_id: str
    ordered_kg: float
    served_kg: float = 0.0

    @property
    def short_kg(self) -> float:
        return round(self.ordered_kg - self.served_kg, 3)


def _ration_buyers(rows: list[Served], mins: dict[str, float], supply: float) -> None:
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
        r.served_kg = round(min(r.ordered_kg, m + (rest * (r.ordered_kg - m) / above if above else 0)), 2)


def _ration_households(rows: list[Served], orders: list[HouseholdOrder], supply: float, day: date) -> None:
    last = {o.household_id: o.last_shorted for o in orders}
    recent = lambda hid: last[hid] is not None and 0 < (day - last[hid]).days <= 7  # noqa: E731
    order = sorted(rows, key=lambda r: (recent(r.customer_id), last[r.customer_id] or date.min, r.customer_id))
    deficit = sum(r.ordered_kg for r in rows) - supply
    for r in rows:
        r.served_kg = r.ordered_kg
    for r in order:
        if deficit <= 1e-9:
            break
        cut = min(r.ordered_kg, deficit)
        r.served_kg = round(r.ordered_kg - cut, 2)
        deficit -= cut


def allocate_day(supply: float, buyers: list[BuyerOrder], households: list[HouseholdOrder],
                 day: date) -> tuple[list[Served], list[Served]]:
    """One line, one day. B2B is served before households (contracts first)."""
    b_rows = [Served(o.buyer_id, o.kg) for o in buyers]
    h_rows = [Served(o.household_id, o.kg) for o in households]
    b2b_need = sum(o.kg for o in buyers)
    if b_rows:
        _ration_buyers(b_rows, {o.buyer_id: o.min_kg for o in buyers}, min(supply, b2b_need))
    left = max(0.0, supply - sum(r.served_kg for r in b_rows))
    if h_rows:
        _ration_households(h_rows, households, left, day)
    return b_rows, h_rows
