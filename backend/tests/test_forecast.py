from datetime import date, timedelta

import pytest

from app.forecast import Series, Signal, active_signals, baseline, forecast

W0 = date(2026, 1, 5)
S = Series("pakcoy", "regular", "B2B", "resto_a")


def weeks(values, start=W0):
    return [(start + timedelta(weeks=i), v) for i, v in enumerate(values)]


def sig(**kw):
    d = dict(id="s", scope="all", effect_pct=-50, week_from=W0, week_to=W0, source="calendar", cause="x")
    d.update(kw)
    return Signal(**d)


def test_flat_history_forecasts_its_level_with_a_band_that_widens():
    hist = weeks([20, 22, 18, 21, 19, 20, 22, 18])
    pts = forecast(hist, S, W0 + timedelta(weeks=8), 4)
    assert pts[0].expected == pytest.approx(20, abs=1.5)
    widths = [p.high - p.low for p in pts]
    assert widths == sorted(widths) and widths[3] == pytest.approx(widths[0] * 2, rel=1e-3)
    assert all(p.low <= p.expected <= p.high for p in pts)


def test_known_past_dip_does_not_drag_the_level():
    dip_week = W0 + timedelta(weeks=7)
    hist = weeks([20] * 7 + [10])
    lebaran = sig(week_from=dip_week, week_to=dip_week, effect_pct=-50, source="note", cause="Lebaran")
    level_without, _ = baseline(hist, S, [])
    level_with, _ = baseline(hist, S, [lebaran])
    assert level_with == pytest.approx(20)
    assert level_without < 18


def test_signal_applies_only_to_matching_weeks_scope_and_crop():
    hist = weeks([20] * 8)
    start = W0 + timedelta(weeks=8)
    s = sig(scope="partner:resto_a", effect_pct=-40, week_from=start + timedelta(weeks=1),
            week_to=start + timedelta(weeks=1), source="note", cause="renovation")
    other_partner = sig(scope="partner:resto_b", effect_pct=-40, week_from=start, week_to=start, source="note")
    other_crop = sig(crop="sawi_putih", week_from=start, week_to=start, source="note")
    pts = forecast(hist, S, start, 3, [s, other_partner, other_crop])
    assert [p.expected for p in pts] == pytest.approx([20, 12, 20])
    assert any("renovation" in r for r in pts[1].reasons)


def test_calendar_is_capped_and_a_note_overrides_it_for_the_same_scope():
    start = W0 + timedelta(weeks=8)
    cal = sig(scope="channel:B2B", effect_pct=-80, week_from=start, week_to=start, source="calendar")
    assert cal.factor() == pytest.approx(0.7)
    note = sig(id="n", scope="channel:B2B", effect_pct=+10, week_from=start, week_to=start, source="note")
    other_scope_cal = sig(id="c2", scope="all", effect_pct=-10, week_from=start, week_to=start)
    act = active_signals(S, start, [cal, note, other_scope_cal])
    assert {s.id for s in act} == {"n", "c2"}


def test_empty_history_forecasts_zero():
    pts = forecast([], S, W0, 2)
    assert [p.expected for p in pts] == [0, 0]
