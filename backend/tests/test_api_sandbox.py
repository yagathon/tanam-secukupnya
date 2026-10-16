from datetime import date
import pytest
from fastapi.testclient import TestClient

from app import farm, gemini, main
from app import sandbox as sb
from app.notes import NoteReading, OrderReading

client = TestClient(main.app)
S = "/api/sandbox"


def _setup(**kw):
    return {**sb.default_setup(), "start": "2026-10-12",
            "buyers": [{"name": "Restaurant A", "type": "business", "line": "regular", "usual_kg_per_week": 14,
                        "weekdays": [1, 4]}],
            "beds": [{"line": "regular", "sown_on": "2026-09-05", "seedlings": 900}], **kw}


def _wipe():
    main.store.for_user("local").reset(sb.SANDBOX)              # setup included: every test starts unsaved
    client.post("/api/demo/reset")


@pytest.fixture(autouse=True)
def fresh():
    _wipe()
    main._g1_cache.clear()
    main._calls.clear()
    yield
    _wipe()


def test_unsaved_setup_blocks_events():
    assert client.get(f"{S}/setup").json()["saved"] is False
    r = client.post(f"{S}/events", json={"form": {"kind": "sow", "line": "regular", "seedlings": 100}, "seq": 1})
    assert r.status_code == 409


def test_setup_then_views_work_and_demo_is_untouched():
    demo_today = client.get("/api/today").json()
    assert client.put(f"{S}/setup", json=_setup()).status_code == 200
    for v in ("state", "today", "beds", "tomorrow", "sow", "demand", "trail"):
        assert client.get(f"{S}/{v}").status_code == 200, v
    assert client.get(f"{S}/state").json()["today"] == "2026-10-12"
    assert client.get("/api/today").json() == demo_today
    assert client.get(f"{S}/state").json()["sandbox"] is True
    assert client.get("/api/state").json()["sandbox"] is False


def test_form_event_then_next_day_and_isolation():
    client.put(f"{S}/setup", json=_setup())
    r = client.post(f"{S}/events", json={"form": {"kind": "order", "buyer": "b1", "line": "regular", "kg": 3,
                                                  "day": "2026-10-13"}, "seq": 1})
    assert r.status_code == 200 and r.json()["lines"] == ["ORDER · Restaurant A · regular · 3.0 kg · Tue 13 Oct"]
    assert client.post(f"{S}/day/next", json={"from_day": "2026-10-12"}).json()["appended"] == 1
    assert client.get(f"{S}/state").json()["today"] == "2026-10-13"
    assert client.post("/api/demo/reset").status_code == 200
    assert client.get(f"{S}/state").json()["today"] == "2026-10-13"           # demo reset keeps the sandbox


def test_double_next_day_and_stale_seq_append_once():           # Review Focus 5
    client.put(f"{S}/setup", json=_setup())
    a = client.post(f"{S}/day/next", json={"from_day": "2026-10-12"}).json()
    b = client.post(f"{S}/day/next", json={"from_day": "2026-10-12"}).json()
    assert (a["appended"], b["appended"]) == (1, 0)
    form = {"kind": "sow", "line": "regular", "seedlings": 100}
    assert client.post(f"{S}/events", json={"form": form, "seq": 2}).status_code == 200
    assert client.post(f"{S}/events", json={"form": form, "seq": 2}).status_code == 409


def test_clear_empties_log_keeps_setup():
    client.put(f"{S}/setup", json=_setup())
    client.post(f"{S}/day/next", json={"from_day": "2026-10-12"})
    client.post(f"{S}/clear")
    assert client.get(f"{S}/state").json()["today"] == "2026-10-12"
    assert client.get(f"{S}/setup").json()["saved"] is True


def test_setup_edit_reruns_log():
    client.put(f"{S}/setup", json=_setup())
    client.post(f"{S}/day/next", json={"from_day": "2026-10-12"})
    before = client.get(f"{S}/sow").json()
    edited = _setup(buyers=[{**_setup()["buyers"][0], "usual_kg_per_week": 70}])
    assert client.put(f"{S}/setup", json=edited).status_code == 200
    assert client.get(f"{S}/state").json()["today"] == "2026-10-13"
    assert client.get(f"{S}/sow").json() != before


def _first_bed_id():
    return sb.reference(sb.SetupIn.model_validate(_setup()).model_dump(mode="json"))["batches"][0]["id"]


def test_setup_edit_breaking_log_is_422_and_keeps_old():           # Review Focus 2
    client.put(f"{S}/setup", json=_setup())
    client.post(f"{S}/events", json={"form": {"kind": "order", "buyer": "b1", "line": "regular", "kg": 3,
                                             "day": "2026-10-13"}, "seq": 1})
    client.post(f"{S}/events", json={"form": {"kind": "harvest", "batch": _first_bed_id(), "kg": 1}, "seq": 2})
    r = client.put(f"{S}/setup", json=_setup(beds=[]))
    assert r.status_code == 422
    assert len(client.get(f"{S}/setup").json()["setup"]["beds"]) == 1


def test_start_locked_once_days_logged():
    client.put(f"{S}/setup", json=_setup())
    client.post(f"{S}/day/next", json={"from_day": "2026-10-12"})
    assert client.get(f"{S}/setup").json()["locked_start"] is True
    assert client.put(f"{S}/setup", json=_setup(start="2026-10-20")).status_code == 422


def test_gemini_note_stores_nothing_before_ok(monkeypatch):
    client.put(f"{S}/setup", json=_setup())
    reading = NoteReading(kind="orders", summary_en="x",
                          orders=[OrderReading(buyer="b1", line="regular", kg=12, day="2026-10-16")])
    monkeypatch.setattr(gemini, "read_note", lambda *a: {"reading": reading, "model": "fake"})
    n = client.post(f"{S}/notes", json={"text": "A 12kg jumat", "sender": "b1"}).json()
    assert n["preview"] == ["ORDER · Restaurant A · regular · 12.0 kg · Fri 16 Oct"]
    assert client.get(f"{S}/trail").json()["rows"][0]["inputs"] == []
    assert client.post(f"{S}/notes/{n['id']}/accept").status_code == 200
    assert client.get(f"{S}/trail").json()["rows"][0]["inputs"] == ["ORDER · Restaurant A · regular · 12.0 kg · Fri 16 Oct"]


def test_400_day_cap():
    client.put(f"{S}/setup", json=_setup())
    ws = sb.open_sandbox(main.store.for_user("local"))
    for i in range(1, 401):
        farm.append(ws, i, {"kind": "day", "events": []})
    r = client.post(f"{S}/day/next", json={"from_day": "2026-10-12"})
    assert r.status_code == 422


def test_order_on_line_buyer_lacks_is_422():
    client.put(f"{S}/setup", json=_setup())
    r = client.post(f"{S}/events", json={"form": {"kind": "order", "buyer": "b1", "line": "baby", "kg": 3,
                                                  "day": "2026-10-13"}, "seq": 1})
    assert r.status_code == 422


def test_setup_edit_orphaning_pending_order_is_422():
    client.put(f"{S}/setup", json=_setup())
    client.post(f"{S}/events", json={"form": {"kind": "order", "buyer": "b1", "line": "regular", "kg": 3,
                                             "day": "2026-10-13"}, "seq": 1})
    moved = _setup(buyers=[{**_setup()["buyers"][0], "line": "baby"}])
    assert client.put(f"{S}/setup", json=moved).status_code == 422
    assert client.put(f"{S}/setup", json=_setup(buyers=[])).status_code == 422
    assert client.post(f"{S}/day/next", json={"from_day": "2026-10-12"}).status_code == 200


def _biz(name):
    return {"name": name, "type": "business", "line": "regular", "usual_kg_per_week": 7}


def _ids(setup):
    return {b["name"]: b["id"] for b in setup["buyers"]}


def test_repasted_buyers_keep_their_ids():                  # a sheet paste sends no ids
    first = client.put(f"{S}/setup", json=_setup(buyers=[_biz("A"), _biz("B"), _biz("C")])).json()["setup"]
    again = client.put(f"{S}/setup", json=_setup(buyers=[_biz("B"), _biz("C")])).json()["setup"]
    assert _ids(again) == {"B": _ids(first)["B"], "C": _ids(first)["C"]}


def test_new_buyer_never_reuses_an_id():
    first = client.put(f"{S}/setup", json=_setup(buyers=[_biz("A"), _biz("B"), _biz("C")])).json()["setup"]
    again = client.put(f"{S}/setup", json=_setup(buyers=[_biz("A"), _biz("B"), _biz("D")])).json()["setup"]
    assert _ids(again)["D"] not in set(_ids(first).values())


def _bed(day, n=500):
    return {"line": "regular", "sown_on": day, "seedlings": n}


def test_adding_an_earlier_bed_keeps_logged_bed_ids():
    first = client.put(f"{S}/setup", json=_setup(beds=[_bed("2026-09-10")])).json()["setup"]
    bid = sb.reference(first)["batches"][0]["id"]
    assert client.post(f"{S}/events", json={"form": {"kind": "harvest", "batch": bid, "kg": 1}, "seq": 1}).status_code == 200
    r = client.put(f"{S}/setup", json=_setup(beds=[_bed("2026-09-01"), *first["beds"]]))
    assert r.status_code == 200
    ref = sb.reference(r.json()["setup"])
    labels = {b["id"]: b["label"] for b in ref["batches"]}
    assert labels[bid] == "Bed 1" and len(set(labels.values())) == 2


def test_same_day_beds_keep_identity_when_reordered():
    a, b = _bed("2026-09-10", 300), _bed("2026-09-10", 700)
    first = client.put(f"{S}/setup", json=_setup(beds=[a, b])).json()["setup"]
    by_n = {x["seedlings"]: x["id"] for x in sb.reference(first)["batches"]}
    again = client.put(f"{S}/setup", json=_setup(beds=[b, a])).json()["setup"]
    assert {x["seedlings"]: x["id"] for x in sb.reference(again)["batches"]} == by_n


def test_edited_bed_keeps_its_id():
    first = client.put(f"{S}/setup", json=_setup()).json()["setup"]
    bid = first["beds"][0]["id"]
    assert client.post(f"{S}/events", json={"form": {"kind": "harvest", "batch": bid, "kg": 1}, "seq": 1}).status_code == 200
    r = client.put(f"{S}/setup", json=_setup(beds=[{**first["beds"][0], "seedlings": 950}]))
    assert r.status_code == 200 and r.json()["setup"]["beds"][0]["id"] == bid


def test_setup_doc_has_no_nested_lists():              # Firestore rejects arrays inside arrays (growth_curve)
    client.put(f"{S}/setup", json=_setup())
    doc = main.store.for_user("local").get("sandbox_setup", sb.SETUP_ID)
    def nested(v, in_list=False):
        if isinstance(v, list):
            return in_list or any(nested(x, True) for x in v)
        return isinstance(v, dict) and any(nested(x) for x in v.values())
    assert not nested(doc)
    assert client.get(f"{S}/setup").json()["setup"]["crop"]["growth_curve"][0] == [0, 5]


def test_legacy_setup_doc_still_opens():
    s = sb.SetupIn.model_validate(_setup()).model_dump(mode="json")
    main.store.for_user("local").put("sandbox_setup", {"id": sb.SETUP_ID, "setup": s})
    assert client.get(f"{S}/setup").json()["saved"] is True


def test_sow_view_follows_setup_sow_weekdays():            # UAT: setup Tue/Fri, Sow tab must not say Mon/Thu
    crop = {**sb.default_setup()["crop"], "sow_weekdays": [1, 4]}
    client.put(f"{S}/setup", json=_setup(crop=crop))       # start Mon 12 Oct → next sowing Tue 13
    assert client.get(f"{S}/state").json()["crop"]["sow_weekdays"] == [1, 4]
    assert {l["day"] for l in client.get(f"{S}/sow").json()["lines"]} == {"2026-10-13"}


def test_demand_view_carries_the_setup_season():
    client.put(f"{S}/setup", json=_setup(month_pct=[40, 20, 20, 20]))
    assert client.get(f"{S}/demand").json()["season"] == {"month_pct": [40, 20, 20, 20], "year_index": [100] * 12}


def _today_line():
    return client.get(f"{S}/today").json()["lines"][0]


def test_today_card_harvest_plan_and_done_flags():
    """Design A: per line, what to harvest from which bed (a prediction, with its basis), and ✓ once logged."""
    client.put(f"{S}/setup", json=_setup())
    client.post(f"{S}/events", json={"form": {"kind": "order", "buyer": "b1", "line": "regular", "kg": 3,
                                             "day": "2026-10-13"}, "seq": 1})
    ln = _today_line()
    assert ln["done"] == {"sown": False, "harvested": False}
    plan = ln["harvest_plan"]
    assert plan and plan[0]["batch"] == _first_bed_id() and plan[0]["label"] == "Bed 1"
    assert sum(p["kg"] for p in plan) == pytest.approx(ln["send_kg"], abs=0.02)
    assert plan[0]["avg_g"] > 0 and plan[0]["sampled"] is False
    assert ln["cover_pct"] == 100 and ln["sellable_from"] is None
    client.post(f"{S}/events", json={"form": {"kind": "harvest", "batch": _first_bed_id(), "kg": 3}, "seq": 2})
    assert _today_line()["done"]["harvested"] is True
    client.post(f"{S}/events", json={"form": {"kind": "sow", "line": "regular", "seedlings": 500}, "seq": 3})
    assert _today_line()["done"]["sown"] is True


def test_today_card_says_when_something_is_sellable_again():
    client.put(f"{S}/setup", json=_setup(beds=[{"line": "regular", "sown_on": "2026-10-01", "seedlings": 900}]))
    client.post(f"{S}/events", json={"form": {"kind": "order", "buyer": "b1", "line": "regular", "kg": 3,
                                             "day": "2026-10-13"}, "seq": 1})
    ln = _today_line()
    assert ln["send_kg"] == 0 and ln["harvest_plan"] == [] and ln["cover_pct"] == 0
    assert ln["sellable_from"] > "2026-10-13"


def test_example_farm_fills_the_form_and_starts_without_a_shortage():
    ex = client.get(f"{S}/example").json()
    assert client.get(f"{S}/setup").json()["saved"] is False        # loading the example saves nothing
    assert ex["start"] == sb.today_wib().isoformat()
    # the founder's farm (saved in the sandbox 2026-10-17): one baby line, one buyer, beds aged 30/23/16/9/2 days
    assert [l["id"] for l in ex["crop"]["lines"]] == ["baby"] and ex["crop"]["growth_curve"][-1] == [35, 250]
    assert ex["month_pct"] == [30, 26, 24, 20] and ex["year_index"][6:8] == [80, 70]
    assert [(b["name"], b["usual_kg_per_week"]) for b in ex["buyers"]] == [("Buyer 1", 35)]
    t = sb.today_wib()
    assert sorted(((t - date.fromisoformat(b["sown_on"])).days, b["seedlings"]) for b in ex["beds"]) == \
        [(2, 500), (9, 1000), (16, 1000), (23, 1000), (30, 1000)]
    assert client.put(f"{S}/setup", json=ex).status_code == 200
    lines = client.get(f"{S}/today").json()["lines"]
    assert sum(l["need_kg"] for l in lines) > 5
    assert all(l["short_kg"] < 0.05 for l in lines)


def test_reset_setup_clears_the_log_and_the_setup():
    client.put(f"{S}/setup", json=_setup())
    client.post(f"{S}/events", json={"form": {"kind": "sow", "line": "regular", "seedlings": 100}, "seq": 1})
    assert client.post(f"{S}/clear", json={"setup": True}).json() == {"ok": True}
    doc = client.get(f"{S}/setup").json()
    assert doc["saved"] is False and doc["setup"]["buyers"] == [] and not doc["locked_start"]


def test_clear_keeps_the_setup():
    client.put(f"{S}/setup", json=_setup())
    client.post(f"{S}/clear")
    assert client.get(f"{S}/setup").json()["saved"] is True
