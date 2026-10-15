from datetime import date

import pytest

from app.growth import (
    crop_from_dict,
    curve,
    curve_inv,
    first_ready_day,
    in_range_mean,
    seeds_for,
    share_from,
)

MON = date(2026, 10, 12)


def test_curve_interpolates_and_extrapolates(pakcoy):
    assert curve(pakcoy, 0) == 5
    assert curve(pakcoy, 21) == 100
    assert curve(pakcoy, 19.5) == pytest.approx(85)       # halfway 70 → 100
    assert curve(pakcoy, -3) == 5                          # flat before the table
    assert curve(pakcoy, 33) == pytest.approx(175)        # last slope (5 g/day) continued


@pytest.mark.parametrize("day", [0, 3.5, 14, 19.5, 22, 30])
def test_curve_inverse_round_trips(pakcoy, day):
    assert curve_inv(pakcoy, curve(pakcoy, day)) == pytest.approx(day)


def test_curve_inverse_clamps(pakcoy):
    assert curve_inv(pakcoy, 1) == 0 and curve_inv(pakcoy, 999) == 30


def test_curve_must_increase():
    with pytest.raises(ValueError):
        crop_from_dict({"id": "x", "name": "x", "nursery_days": 1, "growth_curve": [[0, 5], [7, 5]],
                        "spread_ratio": .4, "germination": .8, "survival": .9, "seeds_per_gram": 1,
                        "grams_per_teaspoon": 1, "max_bed_day": 10, "lines": []})


def test_uniform_spread_shares():
    # avg 100, r 0.4 → plants uniform on [80, 120]
    assert share_from(100, 0.4, 100) == pytest.approx(0.5)
    assert share_from(100, 0.4, 70) == 1.0 and share_from(100, 0.4, 130) == 0.0
    assert share_from(100, 0.0, 100) == 1.0


def test_in_range_mean(pakcoy):
    reg = pakcoy.line("regular")
    assert in_range_mean(120, 0.4, reg) == pytest.approx(120)   # [96,144] ∩ [100,140] → 120
    assert in_range_mean(60, 0.4, reg) == 100                   # nothing in range → nearest edge


def test_first_ready_day_baby_before_regular(pakcoy):
    baby = first_ready_day(pakcoy, pakcoy.line("baby"), MON)
    reg = first_ready_day(pakcoy, pakcoy.line("regular"), MON)
    assert baby < reg == date(2026, 11, 16)                      # 15 nursery + 20 bed days
    assert first_ready_day(pakcoy, pakcoy.line("regular"), MON, offset=2) < reg


def test_seed_conversion(pakcoy):
    g, tsp = seeds_for(pakcoy, 1360)
    assert g == pytest.approx(4.0) and tsp == pytest.approx(1.33)
