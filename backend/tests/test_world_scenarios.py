"""Simulation-report scenarios: the same world, one thing changed at a time."""

from datetime import timedelta

from app import world as W


def test_normal_is_the_default_world():
    a, b = W.build(W.SEED), W.build(W.SEED, "normal")
    assert a.b2b == b.b2b and a.hh == b.hh
    assert a.rain_days == W.RAIN_DAYS and a.pests == (W.PEST,)


def test_every_scenario_has_a_name_and_a_blurb():
    assert list(W.SCENARIOS)[0] == "normal"
    for sc in W.SCENARIOS.values():
        assert sc["name"] and sc["blurb"]


def test_wet_season_adds_rain_and_pests_but_keeps_demand():
    n, w = W.build(W.SEED), W.build(W.SEED, "wet")
    assert w.b2b == n.b2b
    assert len(w.rain_days) > len(n.rain_days) and len(w.pests) > len(n.pests)
    assert all(W.DAY0 < d <= W.DAY0 + timedelta(days=W.FUTURE_DAYS) for d in w.rain_days)


def test_growth_raises_one_restaurant_and_caps_it():
    n, g = W.build(W.SEED), W.build(W.SEED, "growth")
    late = [k for k in n.b2b if k[1] == "resto_b" and k[0] >= (W.DAY0 + timedelta(days=120)).isoformat()]
    ratio = sum(g.b2b[k] for k in late) / sum(n.b2b[k] for k in late)
    assert 1.3 < ratio < 1.5
    before = [k for k in n.b2b if k[0] < W.DAY0.isoformat()]
    assert all(g.b2b[k] == n.b2b[k] for k in before)
    others = [k for k in n.b2b if k[1] == "resto_a"]
    assert all(g.b2b[k] == n.b2b[k] for k in others)


def test_volatile_has_party_orders_after_day0_only():
    n, v = W.build(W.SEED), W.build(W.SEED, "volatile")
    future = [k for k in n.b2b if k[0] > W.DAY0.isoformat()]
    spikes = [k for k in future if n.b2b[k] > 0 and v.b2b[k] > 2 * n.b2b[k]]
    assert len(spikes) >= 10
    before = [k for k in n.b2b if k[0] <= W.DAY0.isoformat()]
    assert all(v.b2b[k] == n.b2b[k] for k in before)
