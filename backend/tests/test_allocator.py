from datetime import date, timedelta

import pytest

from app.allocator import HarvestLot, HouseholdOrder, PartnerOrder, allocate

WEEK = date(2026, 11, 2)


def hh(n, line="regular", kg=1.0, last=None):
    return [HouseholdOrder(f"hh_{i:02d}", line, kg, last(i) if last else None) for i in range(n)]


def test_enough_harvest_serves_everyone_and_counts_surplus_and_waste(crops):
    p = crops["pakcoy"]
    a = allocate(p, WEEK, [HarvestLot("regular", 100, 23)],
                 [PartnerOrder("resto_a", "regular", 30, 20)], hh(10))
    assert a.served_pct == 100
    assert a.waste_kg == pytest.approx(5)  # grade C share 5%
    assert a.surplus_kg == pytest.approx(100 - 5 - 30 - 10)
    assert a.cross_fills == []


def test_b2b_takes_grade_b_first_so_households_keep_grade_a(crops):
    p = crops["pakcoy"]  # best: A 80, B 15, C 5
    a = allocate(p, WEEK, [HarvestLot("regular", 50, 23)],
                 [PartnerOrder("resto_a", "regular", 10, 5)], hh(30))
    # A = 40, B = 7.5 → B2B takes 7.5 B + 2.5 A; households get 37.5 A of 30 ordered
    assert a.partners[0].served_kg == 10
    assert all(h.short_kg == 0 for h in a.households)


def test_short_b2b_gets_minimums_first_then_pro_rata(crops):
    p = crops["pakcoy"]
    a = allocate(p, WEEK, [HarvestLot("regular", 40, 23)],  # 38 kg usable A+B
                 [PartnerOrder("big", "regular", 40, 20), PartnerOrder("small", "regular", 10, 8)], [])
    big, small = a.partners
    assert big.served_kg + small.served_kg == pytest.approx(38)
    assert big.served_kg >= 20 and small.served_kg >= 8
    # remaining 10 kg split by the part above minimum (20 vs 2)
    assert big.served_kg == pytest.approx(20 + 10 * 20 / 22, abs=0.01)


def test_household_shortfall_rotates_and_skips_last_weeks_victims(crops):
    p = crops["pakcoy"]
    last = lambda i: WEEK - timedelta(weeks=1) if i < 3 else (WEEK - timedelta(weeks=4) if i == 5 else None)
    orders = hh(10, last=last)
    a = allocate(p, WEEK, [HarvestLot("regular", 10, 23)], [], orders)  # 8 kg grade A for 10 kg ordered
    assert sum(h.served_kg for h in a.households) == pytest.approx(8)
    shorted = a.shorted_households
    assert len(shorted) == 2
    assert not {"hh_00", "hh_01", "hh_02"} & set(shorted)  # shorted last week → spared
    assert "hh_05" not in shorted  # shorted 4 weeks ago → after never-shorted ones


def test_late_regular_cannot_serve_households_so_baby_cross_fills(crops):
    p = crops["pakcoy"]
    lots = [HarvestLot("regular", 60, 26),  # late zone: fits B2B only
            HarvestLot("baby", 30, 20)]     # early zone: fits B2C
    orders = hh(10, line="regular") + hh(5, line="baby", kg=1.0)
    for i, o in enumerate(orders[10:]):
        orders[10 + i] = HouseholdOrder(f"baby_{i}", "baby", 1.0)
    a = allocate(p, WEEK, lots, [PartnerOrder("resto_a", "regular", 30, 20)], orders)
    assert a.partners[0].served_kg == 30
    fill = [c for c in a.cross_fills if c.to_line == "regular" and c.channel == "B2C"]
    assert fill and fill[0].from_line == "baby" and fill[0].kg == pytest.approx(10)
    assert a.preference_miss_kg == pytest.approx(10)
    assert a.served_pct == 100


def test_lot_outside_every_zone_is_waste(crops):
    a = allocate(crops["pakcoy"], WEEK, [HarvestLot("regular", 20, 30)], [], hh(5))
    assert a.waste_kg == 20 and a.surplus_kg == 0
    assert a.served_pct == 0
