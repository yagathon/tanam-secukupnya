from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"ok": True}


def test_state_has_seed_and_today():
    s = client.get("/api/state").json()
    assert s["today"] == "2026-10-12"
    assert {c["id"] for c in s["crops"]} == {"pakcoy", "sawi_putih"}
    assert s["batches"], "in-ground batches are seeded"


def test_forecast_covers_every_series():
    r = client.post("/api/forecast/run", json={"horizon_weeks": 4}).json()
    keys = {s["key"] for s in r["series"]}
    assert "pakcoy/regular/B2B/resto_a" in keys and "sawi_putih/retail/B2C" in keys
    pt = r["series"][0]["forecast"][0]
    assert pt["low"] <= pt["expected"] <= pt["high"] and pt["reasons"]


def test_plan_shows_planted_bridge_and_shortfall():
    plans = {(p["crop"], p["line"]): p for p in client.post("/api/plan/run", json={}).json()["plans"]}
    regular = plans["pakcoy", "regular"]
    assert any(w["status"] == "bridge" for w in regular["weeks"]), "late transplant → bridge"
    assert regular["recovery_week"] is not None
    retail = plans["sawi_putih", "retail"]
    assert retail["borrow_interest"] is None
    assert any(w["status"] == "shortfall" for w in retail["weeks"]), "failed tray → shortfall"
    assert all(any(w["new_batch"] for w in p["weeks"]) for p in plans.values()), "every line gets a sowing"


def test_scenario_poor_harvest_shorts_someone():
    full = client.post("/api/scenario", json={"crop": "pakcoy", "week": "2026-10-12"}).json()
    poor = client.post("/api/scenario", json={"crop": "pakcoy", "week": "2026-10-12", "harvest_pct": 50}).json()
    assert poor["served_pct"] < full["served_pct"]
    assert poor["harvested_kg"] < full["harvested_kg"]


def test_scenario_unknown_crop():
    assert client.post("/api/scenario", json={"crop": "kangkung", "week": "2026-10-12"}).status_code == 404
