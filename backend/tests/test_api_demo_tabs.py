"""The demo farm carries the sandbox's tabs too: a read-only Setup, Impact against the fixed farmer, the Trail."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)
DAY0 = "2026-10-12"


@pytest.fixture(autouse=True)
def fresh():
    client.post("/api/demo/reset")
    yield
    client.post("/api/demo/reset")


def _days(n):
    assert client.post("/api/day/next", json={"from_day": client.get("/api/state").json()["today"],
                                              "days": n}).json()["appended"] == n


def test_setup_shows_the_demo_farm_as_it_started():
    s = client.get("/api/setup").json()
    assert s["day0"] == DAY0 and s["read_only"] is True
    assert s["crop"]["name"] == "Pakcoy"
    assert len(s["buyers"]) == 5 and len(s["households"]) == 30
    assert s["fixed"] == {"seedlings": {"regular": 1100, "baby": 100}, "weekdays": [0, 3]}
    assert s["beds"] and all(b["sown_on"] < DAY0 for b in s["beds"])
    assert set(s["beds"][0]) >= {"label", "line", "sown_on", "seedlings"}


def test_setup_does_not_move_when_days_pass():
    before = client.get("/api/setup").json()
    _days(3)
    assert client.get("/api/setup").json() == before


def test_impact_and_trail_are_empty_before_the_first_day():
    assert client.get("/api/impact").json()["days"] == 0
    assert len(client.get("/api/trail").json()["rows"]) == 1           # only today's live row


def test_impact_compares_with_the_fixed_farmer_on_mon_and_thu():
    _days(10)                                                         # Mon 12 → Thu 22
    r = client.get("/api/impact").json()
    assert r["days"] == 10
    assert r["habit"]["weekdays"] == [0, 3] and r["habit"]["seedlings"] == {"regular": 1100, "baby": 100}
    assert r["habit"]["label"] == "1,100 regular + 100 baby seedlings every Monday & Thursday"
    habit = [b for b in r["beds"] if b["group"] == "habit"]
    assert {date.fromisoformat(b["sown_on"]).weekday() for b in habit} == {0, 3}
    assert {(b["line"], b["seedlings"]) for b in habit} == {("regular", 1100), ("baby", 100)}
    assert r["rows"]["tanam"]["beds"] > 0


def test_trail_has_one_row_per_closed_day_newest_first():
    _days(3)
    rows = client.get("/api/trail").json()["rows"]
    assert len(rows) == 4 and rows[0]["live"] is True
    assert [r["day"] for r in rows[1:]] == ["2026-10-14", "2026-10-13", DAY0]
