from datetime import date, timedelta

import pytest

from app.planner import Batch, WeekDemand, borrow_interest, harvest_needed, plan_line, split_beds

MON = date(2026, 11, 2)  # a Monday
CAP = {"farmer_a": 14, "farmer_d": 10}


def demand(n, b2b=40.0, b2c=10.0, start=MON):
    return [WeekDemand(start + timedelta(weeks=i), b2b, b2c, b2b * 0.8, b2c * 0.8) for i in range(n)]


def batch_for(crop, line, week, beds, **kw):
    """A batch transplanted so it lands on the Thursday of `week` in its target zone."""
    mid = crop.zone(crop.line(line).target_zone).midpoint
    transplant = week + timedelta(days=3 - mid)
    return Batch(kw.pop("id", f"b{week}"), crop.id, line, "farmer_a", beds,
                 transplant - timedelta(days=crop.nursery_days), transplant, **kw)


def test_harvest_needed_uses_target_zone_grades(crops):
    p = crops["pakcoy"]  # best: A .80, B .15
    assert harvest_needed(p, "regular", 0, 8) == pytest.approx(10)  # B2C needs grade A
    assert harvest_needed(p, "regular", 19, 0) == pytest.approx(20)  # B2B takes A or B
    assert harvest_needed(p, "regular", 19, 8) == pytest.approx(max(10, 27 / 0.95))


def test_borrow_interest_follows_the_zone_before_the_target(crops):
    assert borrow_interest(crops["pakcoy"], "regular") == pytest.approx(1 / 0.75 - 1)
    assert borrow_interest(crops["pakcoy"], "baby") is None
    assert borrow_interest(crops["sawi_putih"], "retail") is None
    assert borrow_interest(crops["sawi_putih"], "restaurant") == pytest.approx(0.10)


def test_split_beds_largest_remainder():
    assert split_beds(5, {"a": 14, "b": 10}) == {"a": 3, "b": 2}
    assert split_beds(1, {"a": 1, "b": 1}) == {"a": 1}
    assert sum(split_beds(17, {"a": 3, "b": 3, "c": 3}).values()) == 17
    assert split_beds(0, {"a": 1}) == {}


def test_empty_ground_far_ahead_sows_every_week(crops):
    p = crops["pakcoy"]
    plan = plan_line(p, "regular", MON - timedelta(days=60), demand(3), [], CAP)
    kg_bed = p.kg_per_bed_for_line("regular")
    for w in plan.weeks:
        assert w.status == "sow" and not w.frozen
        nb = w.new_batch
        assert nb.beds * kg_bed >= w.target_kg > (nb.beds - 1) * kg_bed
        assert nb.harvest_on - nb.seed_by == timedelta(days=p.days_to_harvest("regular"))
        assert nb.harvest_on - nb.transplant_on == timedelta(days=23)
        assert sum(f.beds for f in nb.farmers) == nb.beds
        assert all(f.guaranteed_kg == pytest.approx(f.expected_kg * 0.8, rel=0.01) for f in nb.farmers)


def test_in_ground_is_netted_and_excess_is_flagged(crops):
    p = crops["pakcoy"]
    today = MON - timedelta(days=60)
    full = batch_for(p, "regular", MON, 4, id="b1")  # ~69 kg > ~53 kg target
    plan = plan_line(p, "regular", today, demand(2), [full], CAP)
    assert plan.weeks[0].in_ground_kg == pytest.approx(4 * p.kg_per_bed_for_line("regular"), abs=0.1)
    assert plan.weeks[0].status == "surplus" and plan.weeks[0].net_kg < 0
    assert plan.weeks[1].status == "sow"


def test_pest_note_on_a_batch_raises_the_next_sowing(crops):
    p = crops["pakcoy"]
    today = MON - timedelta(days=60)
    ok = batch_for(p, "regular", MON, 3)
    hit = batch_for(p, "regular", MON, 3, loss_pct=0.4)
    before = plan_line(p, "regular", today, demand(1), [ok], CAP).weeks[0]
    after = plan_line(p, "regular", today, demand(1), [hit], CAP).weeks[0]
    assert after.in_ground_kg < before.in_ground_kg
    assert after.new_batch.beds > before.new_batch.beds


def test_frozen_gap_rolls_forward_with_interest_until_the_recovery_week(crops):
    p = crops["pakcoy"]
    today = MON  # lead time 38 days → the first 5 weeks are frozen
    plan = plan_line(p, "regular", today, demand(7), [], CAP)
    frozen = [w for w in plan.weeks if w.frozen]
    assert len(frozen) == 5 and all(w.status == "bridge" for w in frozen)
    i = 1 / 0.75
    gap = frozen[0].net_kg
    assert frozen[1].bridge_kg == pytest.approx(gap * i + gap, rel=1e-3)
    first_sowable = plan.weeks[5]
    assert plan.recovery_week == first_sowable.week
    assert first_sowable.new_batch.top_up_kg == pytest.approx(first_sowable.bridge_kg)
    assert first_sowable.new_batch.expected_kg >= first_sowable.net_kg + first_sowable.bridge_kg
    assert plan.weeks[6].new_batch.top_up_kg == 0


def test_line_that_cannot_borrow_reports_shortfall(crops):
    s = crops["sawi_putih"]
    plan = plan_line(s, "retail", MON, demand(2, b2b=0, b2c=30), [], {"farmer_c": 18})
    assert [w.status for w in plan.weeks] == ["shortfall", "shortfall"]
    assert plan.recovery_week is None and plan.borrow_interest is None
    assert all(w.bridge_kg == 0 for w in plan.weeks)


def test_surplus_in_a_frozen_week_pays_down_the_bridge(crops):
    p = crops["pakcoy"]
    big = batch_for(p, "regular", MON + timedelta(weeks=1), 8)
    plan = plan_line(p, "regular", MON, demand(3), [big], CAP)
    w0, w1 = plan.weeks[0], plan.weeks[1]
    assert w0.status == "bridge"
    assert w1.net_kg < 0 and w1.bridge_kg < w0.bridge_kg * (1 / 0.75)
