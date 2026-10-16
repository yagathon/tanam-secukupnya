from datetime import date, timedelta

import pytest

from app import demand

D0 = date(2026, 8, 17)  # a Monday


def history(days=56, base=6.0, peak=1.5, drop_from=None, drop=1.0, buyers=("a",), skip_sunday=True):
    out = {}
    for b in buyers:
        s = {}
        for i in range(days):
            d = D0 + timedelta(days=i)
            if skip_sunday and d.weekday() == 6:
                continue
            m = drop if drop_from is not None and i >= drop_from else 1.0
            s[d] = base * (peak if d.weekday() == 5 else 1.0) * m
        out[f"b2b:{b}:regular"] = s
    return out


def test_shape_is_fixed_by_history_before_shape_until():
    h = history()
    shape_until = D0 + timedelta(days=56)
    m1 = demand.fit(h, shape_until, shape_until)
    for i in range(14):  # two more weeks with a different weekday pattern
        d = shape_until + timedelta(days=i)
        h["b2b:a:regular"][d] = 20.0 if d.weekday() == 0 else 1.0
    m2 = demand.fit(h, shape_until, shape_until + timedelta(days=14))
    assert m1.fits["b2b:a:regular"].shape == m2.fits["b2b:a:regular"].shape
    assert m1.fits["b2b:a:regular"].shape[6] == 0          # never orders on Sunday


def test_one_low_order_moves_level_a_little_three_a_lot():
    h = history()
    today = D0 + timedelta(days=56)
    base = demand.fit(h, today, today).fits["b2b:a:regular"].level

    def after(n):
        hh = {k: dict(v) for k, v in h.items()}
        days = [d for d in (today + timedelta(days=i) for i in range(7)) if d.weekday() not in (5, 6)][:n]
        for d in days:
            hh["b2b:a:regular"][d] = 3.0
        return demand.fit(hh, today, days[-1] + timedelta(days=1)).fits["b2b:a:regular"].level

    one, three = after(1), after(3)
    assert base * 0.75 < one < base * 0.95
    assert three < base * 0.65


def test_market_factor_needs_three_buyers_agreeing():
    assert demand.market_factor({"a": [0.8], "b": [0.85]}) == (1.0, 2)
    assert demand.market_factor({"a": [0.8], "b": [0.85], "c": [0.9]})[0] == pytest.approx(0.85)
    assert demand.market_factor({"a": [0.8], "b": [1.2], "c": [0.9], "d": [1.1]})[0] == 1.0   # split
    assert demand.market_factor({"a": [0.98], "b": [0.97], "c": [0.99]})[0] == 1.0           # < 5%


def test_market_drop_lands_in_m_not_levels_and_reaches_unseen_series():
    h = history(days=84, buyers=("a", "b", "c", "d"), drop_from=56, drop=0.85)
    h["hh:regular"] = {d: 2.0 for d in (D0 + timedelta(days=i) for i in range(56))}  # households: no data after
    today, cut = D0 + timedelta(days=84), D0 + timedelta(days=56)
    before = demand.fit(h, cut, cut)
    m = demand.fit(h, cut, today)
    assert before.market == 1.0 and m.market == pytest.approx(0.85, abs=0.03)
    for b in "abcd":   # the drop is carried by m alone: levels end where they were (not counted twice)
        k = f"b2b:{b}:regular"
        assert m.fits[k].level == pytest.approx(before.fits[k].level, rel=0.03)
    mon = today + timedelta(days=(7 - today.weekday()) % 7)
    assert demand.expected(m, "hh:regular", mon) == pytest.approx(2.0 * m.market, rel=0.05)


def test_band_widens_with_horizon():
    h = history()
    for i, d in enumerate(sorted(h["b2b:a:regular"])):
        h["b2b:a:regular"][d] *= 1.1 if i % 2 else 0.9
    today = D0 + timedelta(days=56)
    m = demand.fit(h, today, today)
    mon = today + timedelta(days=7)
    lo1, e1, hi1 = demand.band(m, "b2b:a:regular", mon, 1)
    lo9, e9, hi9 = demand.band(m, "b2b:a:regular", mon, 9)
    assert lo1 < e1 < hi1 and e1 == e9 and hi9 - lo9 > hi1 - lo1


MON = date(2026, 10, 12)


def test_prior_only_key_gets_level_shape_and_wide_sigma():
    m = demand.fit({}, MON, MON, {"b2b:b1:regular": [5, 0, 0, 5, 0, 0, 0]})
    f = m.fits["b2b:b1:regular"]
    assert f.level == 5 and f.shape == [1, 0, 0, 1, 0, 0, 0]
    assert f.sigma == 2.5
    assert demand.expected(m, "b2b:b1:regular", MON + timedelta(days=3)) == 5


def test_prior_zero_jumps_to_first_actual():
    hist = {"b2b:b1:regular": {MON: 8.0}}
    m = demand.fit(hist, MON, MON + timedelta(days=1), {"b2b:b1:regular": [0] * 7})
    assert m.fits["b2b:b1:regular"].level == 8.0


def test_prior_learns_from_zero_days():
    hist = {"b2b:b1:regular": {MON + timedelta(days=7 * i): 0.0 for i in range(3)}}
    m = demand.fit(hist, MON, MON + timedelta(days=15), {"b2b:b1:regular": [10, 0, 0, 0, 0, 0, 0]})
    assert m.fits["b2b:b1:regular"].level < 10


def test_no_priors_is_unchanged(pakcoy):
    from app.state import initial
    from app.store import JsonStore
    ws = JsonStore()
    st = initial({"batches": ws.list("batches"), "history": ws.list("history")}, ws.meta())
    a = demand.fit(st.history, MON, st.today)
    b = demand.fit(st.history, MON, st.today, {})
    assert {k: (f.level, f.sigma) for k, f in a.fits.items()} == {k: (f.level, f.sigma) for k, f in b.fits.items()}


SEASON = {"month_pct": [40, 20, 20, 20], "year_index": [100] * 9 + [150] + [100] * 2}   # October 1.5×


def test_season_factor_blends_month_block_and_year_index():
    assert demand.season_factor(None, date(2026, 10, 3)) == 1.0
    assert demand.season_factor(SEASON, date(2026, 10, 3)) == pytest.approx(1.6 * 1.5)    # 1–7: 40/25
    assert demand.season_factor(SEASON, date(2026, 10, 31)) == pytest.approx(0.8 * 1.5)   # 22–end: 20/25
    assert demand.season_factor(SEASON, date(2026, 11, 8)) == pytest.approx(0.8)          # 8–14, Nov = 100


def test_fit_divides_the_season_out_of_the_level():
    """Orders that follow the setup's season exactly are no surprise: the level stays put, and the
    forecast puts the season back on."""
    start = date(2026, 10, 1)
    pri = {"b2b:a:regular": [10.0] * 7}
    h = {"b2b:a:regular": {start + timedelta(days=i): 10.0 * demand.season_factor(SEASON, start + timedelta(days=i))
                           for i in range(21)}}
    today = start + timedelta(days=21)
    m = demand.fit(h, start, today, pri, SEASON)
    assert m.fits["b2b:a:regular"].level == pytest.approx(10.0, abs=0.01)
    d = date(2026, 11, 2)
    assert demand.expected(m, "b2b:a:regular", d) == pytest.approx(10.0 * 1.6, abs=0.05)
    blind = demand.fit(h, start, today, pri)
    assert abs(blind.fits["b2b:a:regular"].level - 10.0) > 1
