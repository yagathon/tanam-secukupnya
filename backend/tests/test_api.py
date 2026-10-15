import pytest
from fastapi.testclient import TestClient

from app import gemini, main
from app.notes import HarvestReading, NoteReading, OrderReading, SowingReading

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def fresh():
    client.post("/api/demo/reset")
    main._g1_cache.clear()
    main._g5_cache.clear()
    main._calls.clear()
    yield
    client.post("/api/demo/reset")


def fake_gemini(monkeypatch, reading: NoteReading):
    calls = []

    def read_note(text, sender, received_on, ctx):
        calls.append(ctx)
        return {"reading": reading, "model": "fake"}
    monkeypatch.setattr(gemini, "read_note", read_note)
    return calls


def test_state_starts_on_day0():
    s = client.get("/api/state").json()
    assert s["today"] == "2026-10-12" and s["synthetic"]
    assert {"farmer", "operator"} <= {x["id"] for x in s["senders"]}


@pytest.mark.parametrize("path", ["/api/today", "/api/beds", "/api/tomorrow", "/api/sow", "/api/demand"])
def test_views_answer_for_both_lines(path):
    r = client.get(path)
    assert r.status_code == 200
    assert [ln["line"] for ln in r.json()["lines"]] == ["regular", "baby"]


def test_tomorrow_never_sends_more_than_the_ceiling():
    for ln in client.get("/api/tomorrow").json()["lines"]:
        assert ln["send_kg"] <= ln["ceiling_kg"] + 1e-9 <= ln["available_kg"] + 1e-9
        assert sum(b["served_kg"] for b in ln["buyers"]) + sum(h["served_kg"] for h in ln["households"]) \
            <= ln["send_kg"] + 0.05


def test_next_day_is_idempotent_per_from_day():
    r1 = client.post("/api/day/next", json={"from_day": "2026-10-12"}).json()
    r2 = client.post("/api/day/next", json={"from_day": "2026-10-12"}).json()
    assert r1 == {"today": "2026-10-13", "appended": 1} and r2 == {"today": "2026-10-13", "appended": 0}
    assert client.get("/api/state").json()["today"] == "2026-10-13"


def test_next_day_rejects_more_than_14_days():
    assert client.post("/api/day/next", json={"from_day": "2026-10-12", "days": 15}).status_code == 422


def test_reset_returns_to_day0():
    client.post("/api/day/next", json={"from_day": "2026-10-12", "days": 3})
    client.post("/api/demo/reset")
    assert client.get("/api/state").json()["today"] == "2026-10-12"


def test_accepted_order_note_becomes_a_known_order(monkeypatch):
    fake_gemini(monkeypatch, NoteReading(kind="orders", summary_en="Restaurant A wants 15 kg tomorrow", orders=[
        OrderReading(buyer="resto_a", line="regular", kg=15, day="2026-10-13")]))
    n = client.post("/api/notes", json={"text": "besok 15 kg ya", "sender": "resto_a"}).json()
    assert n["status"] == "proposed" and n["proposal"]["orders"][0]["kg"] == 15
    assert len(client.get("/api/today").json()["pending"]) == 1
    a = client.post(f"/api/notes/{n['id']}/accept").json()
    assert a["status"] == "accepted" and a["events"][0]["t"] == "order"
    resto = next(b for b in client.get("/api/tomorrow").json()["lines"][0]["buyers"] if b["id"] == "resto_a")
    assert resto["known"] and resto["ordered_kg"] == 15
    assert client.post(f"/api/notes/{n['id']}/accept").status_code == 409


def test_postponed_sowing_note_lands_on_the_next_sow_day(monkeypatch):
    fake_gemini(monkeypatch, NoteReading(kind="sowing", summary_en="no sowing, rain", sowing=SowingReading(
        line="regular", seedlings=None, postponed=True, reason="heavy rain")))
    n = client.post("/api/notes", json={"text": "hujan, tidak semai", "sender": "farmer"}).json()
    a = client.post(f"/api/notes/{n['id']}/accept").json()
    assert a["events"] == [{"t": "postpone", "line": "regular", "day": "2026-10-12", "reason": "heavy rain"}]
    sow = client.get("/api/sow").json()["lines"][0]
    assert sow["postponed"] == [{"day": "2026-10-12", "reason": "heavy rain"}]


def test_harvest_note_names_a_bed_from_the_context(monkeypatch):
    calls = fake_gemini(monkeypatch, NoteReading(kind="none", summary_en="x"))
    client.post("/api/notes", json={"text": "halo", "sender": "farmer"})
    label = calls[0]["beds"][0]["label"]
    fake_gemini(monkeypatch, NoteReading(kind="harvest", summary_en="x", harvest=HarvestReading(
        bed=label, kg=2, big5_g=None, small5_g=None)))
    n = client.post("/api/notes", json={"text": f"panen {label} 2 kg", "sender": "farmer"}).json()
    assert n["proposal"]["harvest"]["bed"] == label
    assert client.post(f"/api/notes/{n['id']}/accept").status_code == 200


def test_reject_leaves_the_state_alone(monkeypatch):
    fake_gemini(monkeypatch, NoteReading(kind="orders", summary_en="x", orders=[
        OrderReading(buyer="resto_a", line="regular", kg=15, day="2026-10-13")]))
    before = client.get("/api/tomorrow").json()
    n = client.post("/api/notes", json={"text": "besok 15 kg", "sender": "resto_a"}).json()
    assert client.post(f"/api/notes/{n['id']}/reject").json()["status"] == "rejected"
    assert client.get("/api/tomorrow").json() == before


def test_a_note_read_yesterday_cannot_be_accepted_today(monkeypatch):
    fake_gemini(monkeypatch, NoteReading(kind="orders", summary_en="x", orders=[
        OrderReading(buyer="resto_a", line="regular", kg=15, day="2026-10-14")]))
    n = client.post("/api/notes", json={"text": "rabu 15 kg", "sender": "resto_a"}).json()
    client.post("/api/day/next", json={"from_day": "2026-10-12"})
    assert client.post(f"/api/notes/{n['id']}/accept").status_code == 409


def test_unknown_sender_is_422(monkeypatch):
    calls = fake_gemini(monkeypatch, NoteReading(kind="none", summary_en="x"))
    assert client.post("/api/notes", json={"text": "hi", "sender": "ghost"}).status_code == 422
    assert calls == []


def test_same_note_hits_the_cache(monkeypatch):
    calls = fake_gemini(monkeypatch, NoteReading(kind="none", summary_en="x"))
    a = client.post("/api/notes", json={"text": "halo", "sender": "farmer"}).json()
    b = client.post("/api/notes", json={"text": "halo", "sender": "farmer"}).json()
    assert len(calls) == 1 and not a["cached"] and b["cached"]


def test_daily_cap_is_429(monkeypatch):
    fake_gemini(monkeypatch, NoteReading(kind="none", summary_en="x"))
    monkeypatch.setattr(main, "DAILY_CAP", 1)
    assert client.post("/api/notes", json={"text": "satu", "sender": "farmer"}).status_code == 200
    assert client.post("/api/notes", json={"text": "dua", "sender": "farmer"}).status_code == 429


def test_gemini_failure_is_502(monkeypatch):
    def boom(*a):
        raise RuntimeError("down")
    monkeypatch.setattr(gemini, "read_note", boom)
    assert client.post("/api/notes", json={"text": "halo", "sender": "farmer"}).status_code == 502


def test_season_compares_three_strategies():
    s = client.get("/api/season").json()
    assert set(s["summary"]) == {"cobweb", "fixed", "tanam"}
    assert s["summary"]["tanam"]["waste_pct"] < s["summary"]["fixed"]["waste_pct"]
    assert len(s["runs"]) == 3 * len(s["seeds"])


def test_baby_postpone_is_dated_by_the_baby_line_not_regular(monkeypatch):
    fake_gemini(monkeypatch, NoteReading(kind="sowing", summary_en="x", sowing=SowingReading(
        line="regular", seedlings=1200, postponed=False, reason="")))
    n = client.post("/api/notes", json={"text": "semai 1200", "sender": "farmer"}).json()
    client.post(f"/api/notes/{n['id']}/accept")
    fake_gemini(monkeypatch, NoteReading(kind="sowing", summary_en="x", sowing=SowingReading(
        line="baby", seedlings=None, postponed=True, reason="rain")))
    n = client.post("/api/notes", json={"text": "baby ditunda", "sender": "farmer"}).json()
    a = client.post(f"/api/notes/{n['id']}/accept").json()
    assert a["events"] == [{"t": "postpone", "line": "baby", "day": "2026-10-12", "reason": "rain"}]


def _both_at_once(monkeypatch, *calls):
    """Run the calls in two threads, each held after its first state load until both have loaded:
    the window in which two requests both see the same log."""
    import threading

    from app import farm
    barrier, orig, seen = threading.Barrier(len(calls), timeout=10), farm.load, set()

    def gated(ws):
        v = orig(ws)
        me = threading.get_ident()
        if me not in seen:
            seen.add(me)
            barrier.wait()
        return v
    monkeypatch.setattr(farm, "load", gated)
    out = [None] * len(calls)

    def run(i):
        try:
            out[i] = calls[i]()
        except Exception as e:  # noqa: BLE001 - the HTTPException is the result under test
            out[i] = e
    ts = [threading.Thread(target=run, args=(i,)) for i in range(len(calls))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out


def test_two_next_days_at_once_advance_the_farm_once(monkeypatch):
    from datetime import date

    from app import farm
    ws = main.store.for_user("local")
    out = _both_at_once(monkeypatch, *[lambda: farm.next_day(ws, date(2026, 10, 12), 1)] * 2)
    assert sorted(r["appended"] for r in out) == [0, 1]
    assert [d["seq"] for d in ws.list("events")] == [1]


def test_double_accept_applies_the_note_once(monkeypatch):
    fake_gemini(monkeypatch, NoteReading(kind="sowing", summary_en="x", sowing=SowingReading(
        line="regular", seedlings=1200, postponed=False, reason="")))
    n = client.post("/api/notes", json={"text": "semai 1200", "sender": "farmer"}).json()
    ws = main.store.for_user("local")
    out = _both_at_once(monkeypatch, *[lambda: main.accept_note(n["id"], ws)] * 2)
    assert sum(isinstance(r, dict) for r in out) == 1
    assert [e for e in out if not isinstance(e, dict)][0].status_code == 409
    assert len(ws.list("events")) == 1


def test_why_narrates_the_engine_numbers_and_is_cached(monkeypatch):
    seen = []

    def explain(today, tomorrow, sow):
        seen.append(today["today"])
        return {"text": "Because the beds hold enough.", "model": "fake"}
    monkeypatch.setattr(gemini, "explain", explain)
    a = client.post("/api/today/why").json()
    b = client.post("/api/today/why").json()
    assert a["text"] == "Because the beds hold enough." and not a["cached"] and b["cached"]
    assert seen == ["2026-10-12"]


def test_why_with_an_empty_answer_is_an_error_not_a_blank_card(monkeypatch):
    monkeypatch.setattr(gemini, "explain", lambda *a: {"text": "", "model": "fake"})
    r = client.post("/api/today/why")
    assert r.status_code == 502 and "Gemini" in r.json()["detail"]
    assert main._g5_cache == {}
