"""Sowing planner: next sowing = future target − what's already in the ground (MRP-style netting).

One demand line at a time (e.g. pakcoy regular). For every week in the horizon:
1. target   – kg to harvest so the week's demand can be served at the line's target zone grades
2. in-ground – kg the existing batches of this line will yield in that week
3. net = target − in-ground → a new batch (sowable weeks), a bridge (frozen weeks) or a surplus

Lead time decides what sowing can fix. A week is FROZEN when a batch sown today can't reach its
target zone by then; a gap there can only be bridged. Bridging by harvesting the next batch early
is a loan with interest: the early zone yields less (kg_factor below the target zone), so the gap
rolls forward *bigger* each week until the first sowable week, whose batch is topped up to end the
chain (the recovery week). A line whose target zone is the crop's earliest zone can't borrow at all;
its frozen gaps become shortfalls (rotated among households by the allocator).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.crops import Crop

HARVEST_WEEKDAY = 3  # plan harvests on Thursday of the target week


@dataclass(frozen=True)
class Batch:
    """What's in the ground (or the nursery) for one demand line."""

    id: str
    crop: str
    line: str
    farmer_id: str
    beds: float
    seeded_on: date
    transplanted_on: date
    status: str = "bed"  # nursery | bed | harvested | lost
    loss_pct: float = 0.0  # observed damage (from accepted notes)
    harvest_on: date | None = None  # override: borrowed early or held late

    def planned_harvest(self, crop: Crop) -> date:
        if self.harvest_on:
            return self.harvest_on
        return self.transplanted_on + timedelta(days=crop.zone(crop.line(self.line).target_zone).midpoint)

    def expected_kg(self, crop: Crop) -> float:
        if self.status in ("harvested", "lost"):
            return 0.0
        h = self.planned_harvest(crop)
        return crop.harvest_kg(self.beds, (h - self.transplanted_on).days, self.line, self.loss_pct)


@dataclass(frozen=True)
class WeekDemand:
    """Kg to deliver in one week for one line, split by channel. `low_*` = the low band."""

    week: date
    b2b_kg: float = 0.0
    b2c_kg: float = 0.0
    b2b_low_kg: float = 0.0
    b2c_low_kg: float = 0.0


@dataclass
class FarmerShare:
    farmer_id: str
    beds: int
    expected_kg: float
    guaranteed_kg: float  # Trusted Farm's offtake guarantee: their share of the low band


@dataclass
class NewBatch:
    seed_by: date
    transplant_on: date
    harvest_on: date
    beds: int
    expected_kg: float
    farmers: list[FarmerShare] = field(default_factory=list)
    top_up_kg: float = 0.0  # part of the batch that ends a bridge chain


@dataclass
class PlanWeek:
    week: date
    target_kg: float  # kg to harvest
    target_low_kg: float
    in_ground_kg: float
    net_kg: float  # target − in-ground (>0 short, <0 surplus)
    frozen: bool
    status: str  # covered | sow | surplus | bridge | shortfall
    bridge_kg: float = 0.0  # gap carried into this week by borrowing (after interest)
    new_batch: NewBatch | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class Plan:
    crop: str
    line: str
    weeks: list[PlanWeek]
    recovery_week: date | None
    borrow_interest: float | None  # None = this line cannot borrow
    warnings: list[str] = field(default_factory=list)


def harvest_needed(crop: Crop, line_id: str, b2b_kg: float, b2c_kg: float) -> float:
    """Kg to harvest so B2C gets grade A and B2B gets A or B (C is waste)."""
    g = crop.zone(crop.line(line_id).target_zone).grade_share
    need = 0.0
    if b2c_kg:
        need = b2c_kg / g["A"]
    if b2b_kg or b2c_kg:
        need = max(need, (b2b_kg + b2c_kg) / (g["A"] + g["B"]))
    return need


def borrow_interest(crop: Crop, line_id: str) -> float | None:
    """Extra kg owed per kg borrowed by harvesting the next batch in the zone before the target.

    E.g. pakcoy regular targets 'best' (1.0); the earlier zone yields 0.75, so covering 1 kg now
    takes beds that would have given 1/0.75 kg next week: 33% interest. None = no earlier zone.
    """
    target = crop.zone(crop.line(line_id).target_zone)
    earlier = [z for z in crop.zones if z.bed_day_to < target.bed_day_from]
    if not earlier:
        return None
    prev = max(earlier, key=lambda z: z.bed_day_to)
    return target.kg_factor / prev.kg_factor - 1


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def split_beds(beds: int, capacity: dict[str, int]) -> dict[str, int]:
    """Largest-remainder split of `beds` across farmers by bed capacity."""
    total = sum(capacity.values())
    if beds <= 0 or total <= 0:
        return {}
    quotas = {f: beds * c / total for f, c in capacity.items()}
    out = {f: math.floor(q) for f, q in quotas.items()}
    left = beds - sum(out.values())
    for f in sorted(quotas, key=lambda f: (-(quotas[f] - out[f]), f))[:left]:
        out[f] += 1
    return {f: b for f, b in out.items() if b}


def plan_line(crop: Crop, line_id: str, today: date, demand: list[WeekDemand], batches: list[Batch],
              capacity: dict[str, int]) -> Plan:
    """Net the demand of one line against its batches and propose new sowings."""
    line = crop.line(line_id)
    target_zone = crop.zone(line.target_zone)
    kg_per_bed = crop.kg_per_bed_for_line(line_id)
    lead = crop.days_to_harvest(line_id)
    interest = borrow_interest(crop, line_id)
    mine = [b for b in batches if b.crop == crop.id and b.line == line_id]

    rows: list[PlanWeek] = []
    carry = 0.0  # gap rolled forward by borrowing, already including interest
    recovery: date | None = None
    warnings: list[str] = []

    for d in sorted(demand, key=lambda x: x.week):
        wk = week_start(d.week)
        target = harvest_needed(crop, line_id, d.b2b_kg, d.b2c_kg)
        low = harvest_needed(crop, line_id, d.b2b_low_kg, d.b2c_low_kg)
        in_ground = sum(b.expected_kg(crop) for b in mine if week_start(b.planned_harvest(crop)) == wk)
        net = target - in_ground
        harvest_on = wk + timedelta(days=HARVEST_WEEKDAY)
        seed_by = harvest_on - timedelta(days=lead)
        frozen = seed_by < today
        row = PlanWeek(wk, round(target, 1), round(low, 1), round(in_ground, 1), round(net, 1), frozen, "covered")

        if frozen:
            if net <= 0:
                absorbed = min(carry, -net)
                carry -= absorbed
                row.status = "surplus" if net < 0 and absorbed < -net else "covered"
                if absorbed:
                    row.notes.append(f"surplus absorbs {absorbed:.1f} kg of the bridge")
            elif interest is None:
                row.status = "shortfall"
                row.notes.append(f"too late to sow; {crop.name} {line_id} can't be harvested earlier — "
                                 f"short {net:.1f} kg, rotate the shortfall")
            else:
                carry += net
                row.status = "bridge"
                row.notes.append(f"too late to sow; borrow {net:.1f} kg from next week's batch "
                                 f"(costs {interest:.0%} more next week)")
            row.bridge_kg = round(carry, 1)
            if carry and interest:
                carry *= 1 + interest  # borrowed kg comes out of next week, at a worse yield
        else:
            need = net + carry
            top_up = carry
            if need > 0:
                beds = math.ceil(need / kg_per_bed - 1e-9)
                expected = beds * kg_per_bed
                share = split_beds(beds, capacity)
                guarantee_ratio = min(1.0, low / target) if target else 0.0
                farmers = [FarmerShare(f, b, round(b * kg_per_bed, 1), round(b * kg_per_bed * guarantee_ratio, 1))
                           for f, b in share.items()]
                transplant = harvest_on - timedelta(days=target_zone.midpoint)
                row.new_batch = NewBatch(seed_by, transplant, harvest_on, beds, round(expected, 1), farmers,
                                         round(top_up, 1))
                row.status = "sow"
                if top_up:
                    row.notes.append(f"batch includes {top_up:.1f} kg top-up that ends the bridge")
                if beds > sum(capacity.values()):
                    warnings.append(f"{wk}: needs {beds} beds, farmers have {sum(capacity.values())}")
            elif need < 0:
                row.status = "surplus"
                row.notes.append(f"{-need:.1f} kg more than needed already in the ground — tell sales now")
            if carry and recovery is None:
                recovery = wk
            row.bridge_kg = round(carry, 1)
            carry = 0.0
        rows.append(row)

    if carry:
        warnings.append(f"bridge of {carry:.1f} kg not closed within the horizon")
    return Plan(crop.id, line_id, rows, recovery, interest, warnings)
