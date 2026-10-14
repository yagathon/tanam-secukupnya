from datetime import date, timedelta

import pytest

from app.production import (
    Batch,
    apply_loss,
    apply_sample,
    available_kg,
    available_plants,
    bed_day,
    in_bed_plants,
    plants0,
    project,
    shares,
    waste_plants,
)

SOWN = date(2026, 9, 1)


def bd(pakcoy, n):  # the date on bed day n
    return SOWN + timedelta(days=pakcoy.nursery_days + n)


def batch(**kw):
    return Batch(**{"id": "b1", "label": "Bed 1", "line": "regular", "sown_on": SOWN, "seedlings": 1000, **kw})


def test_nothing_ready_in_nursery(pakcoy):
    b = batch()
    assert bed_day(pakcoy, b, SOWN) == -15
    assert shares(pakcoy, b, SOWN) == (0.0, 0.0) and available_kg(pakcoy, b, SOWN) == 0


def test_ready_then_over_then_all_waste(pakcoy):
    b = batch()
    r20, o20 = shares(pakcoy, b, bd(pakcoy, 20))
    r27, o27 = shares(pakcoy, b, bd(pakcoy, 27))
    assert 0 < r20 < r27 == 1.0 and o20 == 0 < o27 < 1
    assert shares(pakcoy, b, bd(pakcoy, 31)) == (1.0, 1.0)
    assert available_plants(pakcoy, b, bd(pakcoy, 31)) == 0
    assert waste_plants(pakcoy, b, bd(pakcoy, 31)) == pytest.approx(plants0(pakcoy, b))


def test_harvested_plants_are_not_wasted(pakcoy):
    b = batch(harvested_plants=600)
    assert waste_plants(pakcoy, b, bd(pakcoy, 31)) == pytest.approx(900 - 600)


def test_sample_sets_offset_spread_and_plants(pakcoy):
    b = batch()
    d = bd(pakcoy, 21)                       # curve says 100 g
    s = apply_sample(pakcoy, b, d, kg=11.0, big5_g=650, small5_g=450)   # avg 110 g, r = 40/110
    assert s.growth_offset_days == pytest.approx(1.2)     # 110 g is curve day 22.2
    assert s.spread_ratio == pytest.approx(0.364, abs=1e-3)
    assert s.harvested_plants == pytest.approx(100)        # 11 kg / 110 g
    assert s.sampled and b.harvested_plants == 0           # the input is not mutated


def test_sample_offset_is_clamped(pakcoy):
    s = apply_sample(pakcoy, batch(), bd(pakcoy, 0), kg=1, big5_g=800, small5_g=700)
    assert s.growth_offset_days == 7


@pytest.mark.parametrize("big,small", [(300, 400), (500, 0), (0, 0)])
def test_sample_rejects_impossible_weights(pakcoy, big, small):
    with pytest.raises(ValueError):
        apply_sample(pakcoy, batch(), bd(pakcoy, 21), kg=1, big5_g=big, small5_g=small)


def test_loss_takes_a_share_of_what_is_in_the_bed(pakcoy):
    b = batch(harvested_plants=100)
    d = bd(pakcoy, 10)
    assert apply_loss(pakcoy, b, d, 30).lost_plants == pytest.approx(0.3 * 800)
    assert apply_loss(pakcoy, b, d, 250).lost_plants == pytest.approx(800)   # clamped to 100%
    assert in_bed_plants(pakcoy, apply_loss(pakcoy, b, d, 100), d) == 0


def test_projection_serves_oldest_first_and_leaves_inputs_alone(pakcoy):
    old = batch(id="old", sown_on=SOWN)
    young = batch(id="young", sown_on=SOWN + timedelta(days=4))
    d = bd(pakcoy, 25)
    need = {d: 5.0}
    proj = project(pakcoy, "regular", [young, old], need, d, d)
    assert proj[0].harvested_kg == pytest.approx(5.0) and proj[0].short_kg == 0
    assert old.harvested_plants == 0 and young.harvested_plants == 0
    from app.production import take_oldest
    taken = take_oldest(pakcoy, [young, old], d, 5.0)
    assert [b.id for b, _ in taken] == ["old"]


def test_projection_counts_shortfall_and_waste(pakcoy):
    b = batch(seedlings=200)
    start, end = bd(pakcoy, 21), bd(pakcoy, 32)
    need = {start + timedelta(days=i): 30.0 for i in range(12)}
    proj = project(pakcoy, "regular", [b], need, start, end)
    assert sum(p.short_kg for p in proj) > 0
    assert sum(p.harvested_kg for p in proj) <= 180 * 0.14 + 1e-6
