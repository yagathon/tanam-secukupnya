from datetime import date, timedelta

import pytest

from app import engine
from app.allocator import BuyerOrder, HouseholdOrder, allocate_day
from app.production import Batch, available_kg, project

TODAY = date(2026, 10, 12)  # Monday
TOM = TODAY + timedelta(days=1)


def farm(seedlings=1100, skip=()):
    """Mon/Thu sowings over the last 46 days (today's not done yet), minus the `skip`ped days."""
    out, d = [], TODAY - timedelta(days=46)
    while d < TODAY:
        if d.weekday() in (0, 3) and d not in skip:
            out.append(Batch(f"regular-{d}", f"Bed {len(out) + 1}", "regular", d, seedlings))
        d += timedelta(days=1)
    return out


def flat(kg, days=60):
    return {TOM + timedelta(days=i): kg for i in range(days)}


def test_ceiling_is_all_available_when_nothing_is_borrowed(pakcoy):
    beds = farm()
    end = engine.horizon_end(pakcoy, "regular", TODAY, False)
    avail = sum(available_kg(pakcoy, b, TOM) for b in beds)
    assert engine.ceiling(pakcoy, "regular", beds, flat(5), TODAY, end) == pytest.approx(avail, abs=0.01)


def test_ceiling_holds_back_when_the_future_runs_short(pakcoy):
    beds = farm()
    end = engine.horizon_end(pakcoy, "regular", TODAY, False)
    need = flat(60)                             # more than 1100 seedlings per sowing can grow
    avail = sum(available_kg(pakcoy, b, TOM) for b in beds)
    c = engine.ceiling(pakcoy, "regular", beds, need, TODAY, end)
    assert 0 < c < avail

    def later_short(x):
        return sum(p.short_kg for p in project(pakcoy, "regular", beds, need, TOM, end, send={TOM: x})[1:])
    assert later_short(c) <= later_short(0) + engine.EPS_KG
    assert later_short(c + 5) > later_short(0) + engine.EPS_KG


def test_borrowing_lists_the_days_that_go_short(pakcoy):
    beds = farm()
    end = engine.horizon_end(pakcoy, "regular", TODAY, False)
    need = flat(60)
    c = engine.ceiling(pakcoy, "regular", beds, need, TODAY, end)
    rows = engine.borrowing(pakcoy, "regular", beds, need, TODAY, end, c + 15, c)
    assert rows and all(r["kg"] > 0 and r["day"] > TOM.isoformat() for r in rows)
    assert engine.borrowing(pakcoy, "regular", beds, need, TODAY, end, c, c) == []


def test_b2b_minimums_first_then_pro_rata_then_households_rotate():
    buyers = [BuyerOrder("a", 10, 6), BuyerOrder("b", 10, 2)]
    hh = [HouseholdOrder("h1", 1, None), HouseholdOrder("h2", 1, TODAY - timedelta(days=3))]
    b, h = allocate_day(12, buyers, hh, TODAY)
    # minimums 6+2 first; the other 4 kg split by what each still wants (4:8)
    assert [r.served_kg for r in b] == [pytest.approx(7.33, abs=0.01), pytest.approx(4.67, abs=0.01)]
    assert [r.served_kg for r in h] == [0, 0]
    b, h = allocate_day(21, buyers, hh, TODAY)
    assert sum(r.served_kg for r in b) == 20
    assert {r.customer_id: r.served_kg for r in h} == {"h1": 0, "h2": 1}   # h2 was shorted 3 days ago


def test_sow_next_is_monday_or_thursday(pakcoy):
    assert engine.next_sow_day(TODAY, False) == TODAY
    assert engine.next_sow_day(TODAY, True) == TODAY + timedelta(days=3)
    assert engine.next_sow_day(TODAY + timedelta(days=1), False) == TODAY + timedelta(days=3)


def test_sow_next_closes_its_coverage_window(pakcoy):
    beds = farm()
    target = flat(34, 70)
    plan = engine.sow_next(pakcoy, "regular", beds, flat(30, 70), target, TODAY, TODAY - timedelta(days=4), False)
    assert plan.day == TODAY and plan.ready_from < plan.covers_until
    assert 0 < plan.seedlings <= 3000 and plan.seedlings % 50 == 0 and not plan.capped
    assert plan.seeds_g == pytest.approx(plan.seedlings / 0.85 / 400, abs=0.05)
    new = Batch("n", "n", "regular", plan.day, plan.seedlings)
    proj = project(pakcoy, "regular", [*beds, new], target, TOM, plan.covers_until)
    assert all(p.short_kg <= 0.05 for p in proj if p.day >= plan.ready_from)


def test_postponed_sowing_grows_the_next_one_and_flags_shortfall_ahead(pakcoy):
    thu = TODAY + timedelta(days=3)
    beds = farm()
    target, prot = flat(34, 70), flat(30, 70)
    on_time = engine.sow_next(pakcoy, "regular", [*beds, Batch("m", "m", "regular", TODAY, 1100)], prot, target,
                              thu, TODAY, False)
    missed = engine.sow_next(pakcoy, "regular", beds, prot, target, thu, TODAY - timedelta(days=4), False)
    assert missed.day == on_time.day == thu
    assert missed.seedlings > on_time.seedlings


def test_missed_sowings_show_up_as_shortfall_ahead(pakcoy):
    gap = {TODAY - timedelta(days=d) for d in (4, 7, 11, 14)}   # two weeks of sowings never happened
    plan = engine.sow_next(pakcoy, "regular", farm(skip=gap), flat(30, 70), flat(34, 70), TODAY,
                           TODAY - timedelta(days=18), False)
    assert plan.shortfall_ahead and all(r["day"] < plan.ready_from.isoformat() for r in plan.shortfall_ahead)
    full = engine.sow_next(pakcoy, "regular", farm(), flat(30, 70), flat(34, 70), TODAY, TODAY - timedelta(days=4), False)
    assert full.shortfall_ahead == []


def test_sow_next_caps_at_farm_capacity(pakcoy):
    plan = engine.sow_next(pakcoy, "regular", farm(), flat(30, 70), flat(500, 70), TODAY, TODAY - timedelta(days=4), False)
    assert plan.capped and plan.seedlings == 3000 and plan.shortfall_ahead


def test_signal_factor_scopes():
    sig = [{"scope": "buyer:resto_a", "line": None, "effect_pct": -50, "date_from": "2026-10-19", "date_to": "2026-10-25"},
           {"scope": "channel:B2C", "line": "baby", "effect_pct": 20, "date_from": "2026-10-01", "date_to": "2026-12-31"}]
    d = date(2026, 10, 20)
    assert engine.signal_factor(sig, "b2b:resto_a:regular", d) == 0.5
    assert engine.signal_factor(sig, "b2b:resto_b:regular", d) == 1.0
    assert engine.signal_factor(sig, "hh:baby", d) == 1.2 and engine.signal_factor(sig, "hh:regular", d) == 1.0
    assert engine.signal_factor(sig, "b2b:resto_a:regular", date(2026, 10, 26)) == 1.0


def test_next_sow_day_custom_weekdays():
    tue = date(2026, 10, 13)
    assert engine.next_sow_day(tue, False, (1, 4)) == tue           # sowing day, not sown yet
    assert engine.next_sow_day(tue, True, (1, 4)) == date(2026, 10, 16)  # Fri


def test_missed_slots_custom_weekdays():
    assert engine.missed_slots(date(2026, 10, 12), date(2026, 10, 19), (2,)) == [date(2026, 10, 14)]


def test_crop_reads_sow_weekdays(pakcoy):
    from app.growth import crop_from_dict
    import json; from app.store import SEED_DIR
    raw = json.loads((SEED_DIR / "crops.json").read_text())[0]
    assert pakcoy.sow_weekdays == (0, 3)
    assert crop_from_dict({**raw, "sow_weekdays": [2]}).sow_weekdays == (2,)
