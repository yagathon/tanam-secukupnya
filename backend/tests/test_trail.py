from app import farm, trail
from app import sandbox as sb
from app.state import replay
from app.store import JsonStore


def _ws():
    base = JsonStore().for_user("t-trail")
    base.reset(sb.SANDBOX)
    s = sb.SetupIn.model_validate({**sb.default_setup(), "start": "2026-10-12",
        "buyers": [{"name": "Restaurant A", "type": "business", "line": "regular", "usual_kg_per_week": 14, "weekdays": [1, 4]}],
        "beds": [{"line": "regular", "sown_on": "2026-09-05", "seedlings": 900}]}).model_dump(mode="json")
    return sb.SandboxStore(base, s)


def test_trail_one_row_per_day_newest_first_plus_live():
    ws = _ws()
    farm.next_day(ws, farm.load(ws).state.today, 2)
    rows = trail.build(ws)["rows"]
    assert [r["day"] for r in rows] == ["2026-10-14", "2026-10-13", "2026-10-12"]
    assert rows[0]["live"] and not rows[1]["live"]
    assert set(rows[1]["lines"]) == {"regular", "baby"}
    assert {"low", "high", "ready", "ceiling", "send", "short", "sow_day", "sow_seedlings"} <= set(rows[1]["lines"]["regular"])


def test_trail_lists_inputs_of_the_day():
    ws = _ws()
    v = farm.load(ws)
    farm.append(ws, v.log_key[1] + 1, {"kind": "form", "events": [
        {"t": "order", "day": "2026-10-13", "buyer": "b1", "line": "regular", "kg": 3.0}]})
    farm.next_day(ws, farm.load(ws).state.today, 1)
    rows = trail.build(ws)["rows"]
    assert rows[1]["inputs"] == ["ORDER · Restaurant A · regular · 3.0 kg · Tue 13 Oct"]


def test_trail_is_incremental():
    ws = _ws()
    farm.next_day(ws, farm.load(ws).state.today, 1)
    trail.build(ws)
    farm.next_day(ws, farm.load(ws).state.today, 1)
    assert trail.build(ws)["replayed_from"] > 0


def _form_and_day(ws, kg):
    farm.append(ws, 1, {"kind": "form", "events": [
        {"t": "order", "day": "2026-10-13", "buyer": "b1", "line": "regular", "kg": kg}]})
    farm.next_day(ws, farm.load(ws).state.today, 1)


def test_clear_then_same_seqs_is_not_served_from_cache():        # a sandbox clear reuses seq numbers
    ws = _ws()
    _form_and_day(ws, 3.0)
    assert trail.build(ws)["rows"][1]["inputs"]
    farm.load(ws)
    # another instance clears and refills to the same seqs; this process never sees the empty log
    other = sb.SandboxStore(JsonStore().for_user("t-trail-other"), ws.setup)
    other.reset(sb.SANDBOX)
    _form_and_day(other, 5.0)
    ws.reset(sb.SANDBOX)
    for d in sorted(other.list("events"), key=lambda d: d["seq"]):
        ws.add("events", d)
    assert trail.build(ws)["rows"][1]["inputs"] == ["ORDER · Restaurant A · regular · 5.0 kg · Tue 13 Oct"]
    fresh = replay({"batches": ws.list("batches"), "history": ws.list("history")}, ws.meta(), farm.crop(ws),
                   ws.list("events"))
    assert farm.load(ws).state.known_orders == fresh.known_orders
