"""Reference-curve learning wired through state.apply (model B, layer 2)."""

import pytest

from app import calibration as cal
from app.growth import curve
from app.production import bed_day
from app.state import apply, current_crop, initial
from app.store import JsonStore

T = 21  # the bed day the samples aim at; the seed may not have one exactly, so take the nearest


def _state(learn=True):
    ws = JsonStore()
    return initial({"batches": ws.list("batches"), "history": ws.list("history")},
                   {**ws.meta(), "learn_reference": learn})


def _bed(st, crop):
    return min(sorted(st.batches.values(), key=lambda b: b.id), key=lambda b: abs(bed_day(crop, b, st.today) - T))


def _sample(st, crop, b, kg=5):
    apply(st, crop, {"t": "harvest", "batch": b.id, "day": st.today.isoformat(), "kg": kg,
                     "big5_g": 650, "small5_g": 550})  # avg 120 g


def test_sample_teaches_reference_when_learning(pakcoy):
    st = _state()
    b = _bed(st, pakcoy)
    t = bed_day(pakcoy, b, st.today)
    want, _ = cal.update(pakcoy.curve, (), t, 120 / curve(pakcoy, t))
    _sample(st, pakcoy, b)
    cur = current_crop(st, pakcoy)
    assert [y for _, y in cur.curve] == pytest.approx([y for _, y in want])
    assert cur.curve != pakcoy.curve
    assert st.batches[b.id].size_factor == pytest.approx(round(120 / curve(cur, t), 3))   # re-anchored
    assert st.ref_log[-1]["node_days"] == [x for (x, y0), (_, y1) in zip(pakcoy.curve, want) if y0 != y1]


def test_no_learning_in_demo(pakcoy):
    st = _state(learn=False)
    _sample(st, pakcoy, _bed(st, pakcoy))
    assert current_crop(st, pakcoy) is pakcoy


def test_lost_bed_does_not_teach(pakcoy):
    st = _state()
    b = _bed(st, pakcoy)
    apply(st, pakcoy, {"t": "loss", "batch": b.id, "day": st.today.isoformat(), "pct": 20, "cause": "pest"})
    _sample(st, pakcoy, b, kg=2)
    assert current_crop(st, pakcoy) is pakcoy


def test_nursery_sample_does_not_teach(pakcoy):           # Review Focus 4
    st = _state()
    b = next(b for b in st.batches.values() if bed_day(pakcoy, b, st.today) < 0)
    apply(st, pakcoy, {"t": "harvest", "batch": b.id, "day": st.today.isoformat(), "kg": 0.1,
                       "big5_g": 50, "small5_g": 40})
    assert current_crop(st, pakcoy) is pakcoy
    assert 0.5 <= st.batches[b.id].size_factor <= 1.5


def test_reference_reset_restores_start(pakcoy):
    st = _state()
    _sample(st, pakcoy, _bed(st, pakcoy))
    apply(st, pakcoy, {"t": "reference_reset", "day": st.today.isoformat()})
    assert current_crop(st, pakcoy) is pakcoy and st.ref_kept == ()


def test_harvest_is_recorded_per_day_and_line(pakcoy):
    st = _state(learn=False)
    b = _bed(st, pakcoy)
    apply(st, pakcoy, {"t": "harvest", "batch": b.id, "day": st.today.isoformat(), "kg": 5})
    assert st.harvested[st.today.isoformat(), b.line] == 5
