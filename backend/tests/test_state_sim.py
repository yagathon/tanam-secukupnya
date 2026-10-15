import copy
from datetime import timedelta

import pytest

from app import sim
from app import world as W
from app.state import replay, to_ref


@pytest.fixture(scope="module")
def start(pakcoy):
    return sim.warmup(pakcoy, W.build(W.SEED))


def test_warmup_lands_on_day0_with_full_beds_and_8_weeks_of_history(start):
    st, fixed = start
    assert st.today == W.DAY0
    assert fixed == {"regular": 1100, "baby": 100}
    assert min(min(s) for s in st.history.values()) >= W.DAY0 - timedelta(days=W.HISTORY_DAYS)
    assert len(st.batches) > 10


def test_replaying_the_logged_days_rebuilds_the_same_state(pakcoy, start):
    st0, fixed = start
    ref, meta = to_ref(st0)
    st, w, docs = copy.deepcopy(st0), W.build(W.SEED), []
    for seq in range(1, 6):
        docs.append({"seq": seq, "kind": "day", "events": sim.step(st, pakcoy, w, "tanam", fixed)})
    again = replay(ref, meta, pakcoy, list(reversed(docs)))      # replay sorts by seq
    assert again.today == st.today == W.DAY0 + timedelta(days=5)
    assert again.batches == st.batches
    assert again.history == st.history and again.known_orders == st.known_orders


def test_a_rain_day_postpones_instead_of_sowing(pakcoy, start):
    st, fixed = copy.deepcopy(start[0]), start[1]
    w = W.build(W.SEED)
    while st.today < W.RAIN_DAYS[0]:
        sim.step(st, pakcoy, w, "fixed", fixed)
    evs = sim.day_events(st, pakcoy, w, "fixed", fixed)
    assert {e["t"] for e in evs} >= {"postpone"} and not [e for e in evs if e["t"] == "sow"]


def test_short_season_tanam_wastes_less_than_cobweb_and_fixed(pakcoy, start):
    w = W.build(W.SEED)
    r = {s: sim.season(pakcoy, w, s, days=70, start=start) for s in sim.STRATEGIES}
    # cobweb looks lean early and only starves buyers later, so compare tanam against each, not them to each other
    assert r["tanam"]["waste_pct"] < min(r["fixed"]["waste_pct"], r["cobweb"]["waste_pct"])
    assert r["tanam"]["b2b_fill_pct"] >= 95
