import pytest

from app.crops import crop_from_dict


def test_pakcoy_best_bed_is_about_19kg(crops):
    assert crops["pakcoy"].kg_per_bed == pytest.approx(19.2)


def test_zone_lookup_and_waste(crops):
    p = crops["pakcoy"]
    assert p.zone_at(18) is None  # too early
    assert p.zone_at(19).name == "early"
    assert p.zone_at(23).name == "best"
    assert p.zone_at(27).name == "late"
    assert p.zone_at(28) is None  # waste


def test_harvest_kg_applies_zone_pest_and_observed_loss(crops):
    s = crops["sawi_putih"]
    best = s.harvest_kg(1, 55)
    assert best == pytest.approx(55 * 0.9)
    late = s.harvest_kg(1, 70)  # very_late: +20% kg, pest 10% + 10%
    assert late == pytest.approx(55 * 1.2 * 0.8)
    assert s.harvest_kg(1, 55, loss_pct=0.3) == pytest.approx(best * 0.7)
    assert s.harvest_kg(1, 80) == 0


def test_baby_line_planted_closer_yields_less_per_bed(crops):
    p = crops["pakcoy"]
    baby, regular = p.kg_per_bed_for_line("baby"), p.kg_per_bed_for_line("regular")
    assert baby == pytest.approx(19.2 * 1.5 * 0.75 * 0.9)
    # per bed-day baby is competitive: it frees the bed ~3 days sooner
    assert p.days_to_harvest("baby") < p.days_to_harvest("regular")


def test_lead_time_fast_vs_slow_crop(crops):
    assert crops["pakcoy"].days_to_harvest("regular") == 15 + 23
    assert crops["sawi_putih"].days_to_harvest("retail") == 15 + 55


def _profile(**over):
    d = {
        "id": "x", "name": "X", "nursery_days": 10, "plants_per_bed": 10,
        "grams_per_plant": 100, "pest_loss": 0.1,
        "zones": [{"name": "best", "bed_day_from": 5, "bed_day_to": 7, "kg_factor": 1,
                   "grade_share": {"A": 1, "B": 0, "C": 0}, "fits": ["B2C"]}],
        "demand_lines": [{"id": "l", "channels": ["B2C"], "target_zone": "best"}],
    }
    d.update(over)
    return d


def test_validation_rejects_bad_profiles():
    crop_from_dict(_profile())
    with pytest.raises(ValueError, match="overlap"):
        crop_from_dict(_profile(zones=_profile()["zones"] * 2))
    with pytest.raises(ValueError, match="sum to 1"):
        z = dict(_profile()["zones"][0], grade_share={"A": 0.5, "B": 0, "C": 0})
        crop_from_dict(_profile(zones=[z]))
    with pytest.raises(KeyError):
        crop_from_dict(_profile(demand_lines=[{"id": "l", "channels": ["B2C"], "target_zone": "nope"}]))
