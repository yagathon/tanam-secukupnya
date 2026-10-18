"""Impact: the sandbox as logged vs. the same days under the old habit (fixed seedlings once a week)."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app import sandbox as sb

client = TestClient(main.app)
S = "/api/sandbox"


def _setup(**kw):
    return {**sb.default_setup(), "start": "2026-10-12",          # a Monday
            "buyers": [{"name": "Restaurant A", "type": "business", "line": "regular", "usual_kg_per_week": 14,
                        "weekdays": [1, 4]}],
            "beds": [{"line": "regular", "sown_on": "2026-09-05", "seedlings": 900}], **kw}


@pytest.fixture(autouse=True)
def fresh():
    main.store.for_user("local").reset(sb.SANDBOX)
    yield
    main.store.for_user("local").reset(sb.SANDBOX)


def _form(f):
    seq = client.get(f"{S}/today").json()["seq"]
    r = client.post(f"{S}/events", json={"form": f, "seq": seq})
    assert r.status_code == 200, r.text


def _days(n):
    while n > 0:
        day = client.get(f"{S}/today").json()["today"]
        step = min(n, 14)
        assert client.post(f"{S}/day/next", json={"from_day": day, "days": step}).json()["appended"] == step
        n -= step


def test_impact_before_setup_is_409():
    assert client.get(f"{S}/impact").status_code == 409


def test_habit_sows_its_seedlings_once_a_week_on_thursday():
    client.put(f"{S}/setup", json=_setup())
    _days(14)                                                     # Mon 12 → Mon 26: Thursdays 15 and 22
    r = client.get(f"{S}/impact").json()
    lines = len(sb.default_setup()["crop"]["lines"])                # the habit sows every line
    assert r["habit"]["weekdays"] == [3] and set(r["habit"]["seedlings"].values()) == {1000}
    assert r["habit"]["label"] == "1,000 seedlings every Thursday" and len(r["habit"]["seedlings"]) == lines
    assert r["rows"]["habit"]["beds"] == 2 * lines and r["rows"]["habit"]["seedlings"] == 2000 * lines
    assert r["rows"]["tanam"]["beds"] == 0                        # nothing sown in the log
    assert r["rows"]["before"]["beds"] == 1 and r["rows"]["before"]["seedlings"] == 900


def test_habit_delivers_the_same_kg_or_counts_what_it_could_not():
    client.put(f"{S}/setup", json=_setup())
    _form({"kind": "sow", "line": "regular", "seedlings": 400})
    _days(30)
    d = client.get(f"{S}/impact").json()["delivery"]
    assert d["logged_kg"] > 0
    assert d["habit_kg"] + d["habit_short_kg"] == pytest.approx(d["logged_kg"], abs=0.05)


def test_oversowing_habit_wastes_more_than_a_sowing_sized_to_demand():
    client.put(f"{S}/setup", json=_setup())
    _form({"kind": "sow", "line": "regular", "seedlings": 300})
    _days(45)
    r = client.get(f"{S}/impact").json()
    assert r["rows"]["habit"]["waste_plants"] > r["rows"]["tanam"]["waste_plants"]
    assert sum(b["waste"] for b in r["beds"] if b["group"] == "habit") == r["rows"]["habit"]["waste_plants"]

def test_a_logged_loss_hits_the_habit_bed_of_the_same_age():
    client.put(f"{S}/setup", json=_setup())
    _form({"kind": "sow", "line": "regular", "seedlings": 500})
    _days(20)
    bed = next(b for b in client.get(f"{S}/beds").json()["lines"][0]["batches"] if b["sown_on"] == "2026-10-12")
    _form({"kind": "loss", "batch": bed["id"], "pct": 50, "cause": "rain"})
    rows = client.get(f"{S}/impact").json()["rows"]
    assert rows["tanam"]["lost_plants"] > 0
    assert rows["habit"]["lost_plants"] > 0


def _beds(group):
    return [b for b in client.get(f"{S}/impact").json()["beds"] if b["group"] == group]


def test_every_bed_is_one_bar_of_harvested_lost_wasted_and_still_growing():
    client.put(f"{S}/setup", json=_setup())
    _form({"kind": "sow", "line": "regular", "seedlings": 300})
    _days(3)
    [bed] = _beds("tanam")
    assert set(bed) == {"id", "label", "line", "sown_on", "group", "seedlings", "harvested", "lost", "waste",
                        "growing", "closed_on"}
    assert bed["waste"] == 0 and bed["closed_on"] is None and bed["growing"] == 270     # 300 × survival 0.9
    assert {b["group"] for b in client.get(f"{S}/impact").json()["beds"]} == {"before", "tanam", "habit"}


def test_a_bed_past_selling_size_sends_all_it_still_holds_to_waste():
    client.put(f"{S}/setup", json=_setup())
    _days(40)
    [bed] = _beds("before")
    assert bed["closed_on"] is not None and bed["growing"] == 0
    assert bed["waste"] > 0
    assert bed["waste"] == pytest.approx(900 * 0.9 - bed["harvested"] - bed["lost"], abs=1)


def test_a_bed_cut_empty_before_it_outgrows_wastes_nothing():
    client.put(f"{S}/setup", json=_setup())
    bed = client.get(f"{S}/beds").json()["lines"][0]["batches"][0]
    _form({"kind": "harvest", "batch": bed["id"], "kg": 5, "empty": True})
    _days(40)
    [bed] = _beds("before")
    assert bed["waste"] == 0 and bed["growing"] == 0


def test_a_recount_corrects_only_the_real_bed_not_the_habit():
    client.put(f"{S}/setup", json=_setup())
    _form({"kind": "sow", "line": "regular", "seedlings": 500})
    _days(20)
    bed = next(b for b in client.get(f"{S}/beds").json()["lines"][0]["batches"] if b["sown_on"] == "2026-10-12")
    _form({"kind": "harvest", "batch": bed["id"], "kg": 1, "empty": True})   # "the bed is empty": a count fix, not a pest
    rows = client.get(f"{S}/impact").json()["rows"]
    assert rows["tanam"]["lost_plants"] > 0
    assert rows["habit"]["lost_plants"] == 0
