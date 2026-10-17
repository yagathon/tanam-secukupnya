"""The UI (frontend/lib/types.ts) reads exactly these keys. If a route changes shape, this fails first."""

import pytest
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def fresh():
    client.post("/api/demo/reset")
    yield
    client.post("/api/demo/reset")


def keys(d: dict) -> set[str]:
    return set(d)


def test_state_shape():
    s = client.get("/api/state").json()
    assert keys(s) >= {"today", "synthetic", "crop", "buyers", "households", "senders"}
    assert keys(s["crop"]) >= {"name", "lines", "nursery_days", "germination", "survival"}
    assert keys(s["buyers"][0]) >= {"id", "alias", "segment", "lines"}
    assert keys(s["senders"][0]) == {"id", "alias"}


def test_today_shape():
    t = client.get("/api/today").json()
    assert keys(t) == {"today", "weekday", "lines", "pending", "seq"}
    assert t["seq"] == 1                                    # the seq the next logged event takes
    ln = t["lines"][0]
    assert keys(ln) == {"line", "need_kg", "ceiling_kg", "send_kg", "short_kg", "rotated", "sow",
                        "done", "demand", "extra_kg", "harvest_plan", "cover_pct", "sellable_from"}
    assert keys(ln["done"]) == {"sown", "harvested"}
    assert keys(ln["sow"]) == {"day", "weekday", "seedlings", "seeds_g", "teaspoons", "shortfall_ahead_kg"}


def test_beds_shape():
    b = client.get("/api/beds").json()["lines"][0]
    assert keys(b) == {"line", "min_g", "max_g", "stretch_g", "batches", "past", "chart"}
    assert keys(b["batches"][0]) == {"id", "label", "sown_on", "bed_day", "stage", "seedlings", "plants_left", "avg_g",
                                     "size_pct", "spread", "sampled", "ready_from", "until",
                                     "available_tomorrow_kg", "waste_plants"}
    assert keys(b["chart"][0]) == {"day", "available_kg", "need_kg", "short_kg"}
    assert len(b["chart"]) == 40


def test_tomorrow_shape():
    ln = client.get("/api/tomorrow").json()["lines"][0]
    assert keys(ln) == {"line", "day", "need_kg", "available_kg", "ceiling_kg", "send_kg", "short_kg", "buyers",
                        "households", "borrowing"}
    assert keys(ln["buyers"][0]) == {"id", "alias", "known", "ordered_kg", "served_kg", "min_kg"}
    assert keys(ln["households"][0]) == {"id", "alias", "ordered_kg", "served_kg"}


def test_sow_shape():
    ln = client.get("/api/sow").json()["lines"][0]
    assert keys(ln) == {"line", "day", "seedlings", "seeds_g", "teaspoons", "ready_from", "covers_until", "gap_kg",
                        "capped", "shortfall_ahead", "missed", "postponed", "basis"}


def test_demand_shape():
    d = client.get("/api/demand").json()
    assert keys(d) == {"today", "market", "series", "signals", "lines", "season"}
    assert d["season"] is None                                   # the demo world has no setup season
    assert keys(d["market"]) == {"factor", "buyers", "text"}
    assert keys(d["series"][0]) == {"key", "label", "line", "usual_kg", "level_kg", "shape"}
    assert keys(d["lines"][0]["days"][0]) == {"day", "low", "expected", "high", "protected", "target"}


def test_season_shape():
    s = client.get("/api/season").json()
    assert keys(s) >= {"days", "seeds", "main_seed", "summary", "runs", "sowings", "synthetic"}
    assert set(s["summary"]) == {"cobweb", "fixed", "tanam"}
    assert keys(s["summary"]["tanam"]) == {"waste_pct", "b2b_fill_pct", "hh_fill_pct", "sowing_cv"}
    assert keys(s["runs"][0]) == {"strategy", "seed", "waste_pct", "b2b_fill_pct", "hh_fill_pct", "sowing_cv"}
    assert keys(s["sowings"]["tanam"][0]) == {"line", "day", "seedlings"}


def test_next_day_shape():
    r = client.post("/api/day/next", json={"from_day": "2026-10-12"}).json()
    assert r == {"today": "2026-10-13", "appended": 1}
    assert client.post("/api/day/next", json={"from_day": "2026-10-12"}).json() == {"today": "2026-10-13", "appended": 0}
