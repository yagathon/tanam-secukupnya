from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app import sandbox as sb
from app.growth import crop_from_dict
from app.state import replay
from app.store import JsonStore


def setup(**kw):
    s = sb.default_setup()
    s.update(kw)
    return sb.SetupIn.model_validate(s).model_dump(mode="json")


def test_default_setup_is_valid_and_blank():
    s = setup()
    assert s["buyers"] == [] and s["beds"] == [] and s["learn_reference"] is True


@pytest.mark.parametrize("bad", [
    {"crop": {**sb.default_setup()["crop"], "growth_curve": [[0, 5]]}},                     # < 2 points
    {"crop": {**sb.default_setup()["crop"], "growth_curve": [[0, 5], [7, 4]]}},             # not increasing
    {"crop": {**sb.default_setup()["crop"], "lines": [{"id": "r", "min_g": 100, "max_g": 90}]}},
    {"buyers": [{"name": "A", "type": "business", "line": "nope", "usual_kg_per_week": 1}]},
    {"buyers": [{"name": "A", "type": "business", "line": "regular"}] * 2},                  # duplicate name
    {"buyers": [{"name": f"B{i}", "type": "household", "line": "regular"} for i in range(51)]},
    {"beds": [{"line": "regular", "sown_on": "2099-01-01", "seedlings": 10}]},              # after start
])
def test_setup_rejects(bad):
    with pytest.raises(ValidationError):
        sb.SetupIn.model_validate({**sb.default_setup(), **bad})


def test_buyer_ids_assigned():
    s = setup(buyers=[{"name": "Restaurant A", "type": "business", "line": "regular", "usual_kg_per_week": 14}])
    assert s["buyers"][0]["id"] == "b1"


def test_reference_priors_and_households():
    s = setup(buyers=[
        {"name": "Restaurant A", "type": "business", "line": "regular", "usual_kg_per_week": 10, "weekdays": [1, 4]},
        {"name": "H1", "type": "household", "line": "regular", "usual_kg_per_week": 7},
        {"name": "H2", "type": "household", "line": "regular", "usual_kg_per_week": 1, "weekdays": [5]},
    ])
    ref = sb.reference(s)
    pri = ref["meta"]["priors"]
    assert pri["b2b:b1:regular"] == [0, 5, 0, 0, 5, 0, 0]
    assert pri["hh:regular"] == [1, 1, 1, 1, 1, 2, 1]
    assert ref["meta"]["household_ids"] == ["b2", "b3"]
    assert ref["buyers"][0]["lines"]["regular"]["min_kg"] == 0
    assert ref["history"] == []


def test_existing_beds_become_batches():
    s = setup(start="2026-10-16", beds=[{"line": "regular", "sown_on": "2026-09-20", "seedlings": 800}])
    b = sb.reference(s)["batches"][0]
    assert b["label"] == "Bed 1" and b["seedlings"] == 800 and b["sown_on"] == "2026-09-20"
    assert sb.reference(s)["meta"]["next_bed"] == 2


def _sandbox(s):
    base = JsonStore().for_user("t-sb")
    base.reset(sb.SANDBOX)
    return sb.SandboxStore(base, s)


def test_sandbox_store_maps_collections():
    ws = _sandbox(setup())
    ws.put("events", {"seq": 1, "kind": "day", "events": []})
    assert ws.uid.endswith("#sandbox")
    assert len(ws.base.list("sandbox_events")) == 1 and ws.base.list("events") == []
    assert ws.meta()["sandbox"] is True and ws.list("history") == []


def _state(s, docs=()):
    ref = sb.reference(s)
    c = crop_from_dict(ref["crops"][0])
    return replay({"batches": ref["batches"], "history": ref["history"]}, ref["meta"], c, list(docs)), c, ref


def test_close_day_with_nothing_set_up():                      # Review Focus 3
    s = setup()
    st, c, ref = _state(s)
    from app import sim
    evs = sb.close_day(st, c, ref["buyers"], ref["households"], sim.plan(st, c, ref["buyers"]))
    assert evs[-1] == {"t": "clock", "day": (st.today + timedelta(days=1)).isoformat()}
    assert not [e for e in evs if e["t"] in ("harvest", "short")]


def test_close_day_zero_fills_regular_weekday_and_serves_orders():
    start = date(2026, 10, 12)                                   # Monday → closes into Tuesday
    s = setup(start=start.isoformat(),
              buyers=[{"name": "Restaurant A", "type": "business", "line": "regular", "usual_kg_per_week": 10, "weekdays": [1, 4]},
                      {"name": "Caterer B", "type": "business", "line": "regular", "usual_kg_per_week": 5, "weekdays": [1]}],
              beds=[{"line": "regular", "sown_on": "2026-09-01", "seedlings": 1000}])
    order = {"t": "order", "day": "2026-10-13", "buyer": "b1", "line": "regular", "kg": 4.0}
    st, c, ref = _state(s, [{"seq": 1, "kind": "form", "events": [order]}])
    from app import sim
    evs = sb.close_day(st, c, ref["buyers"], ref["households"], sim.plan(st, c, ref["buyers"]))
    acts = {e["series"]: e["kg"] for e in evs if e["t"] == "actual"}
    assert acts["b2b:b1:regular"] == 4.0 and acts["b2b:b2:regular"] == 0.0
    served = next(e for e in evs if e["t"] == "served" and e["line"] == "regular")
    assert served["b2b_ordered"] == 4.0
    assert [e for e in evs if e["t"] == "harvest"]               # assumed harvest of the planned send


def test_logged_harvest_replaces_assumed_one():
    start = date(2026, 10, 12)
    s = setup(start=start.isoformat(),
              buyers=[{"name": "Restaurant A", "type": "business", "line": "regular", "usual_kg_per_week": 10, "weekdays": [1]}],
              beds=[{"line": "regular", "sown_on": "2026-09-01", "seedlings": 1000}])
    st0, c, ref = _state(s)
    bid = next(iter(st0.batches))
    docs = [{"seq": 1, "kind": "form", "events": [
        {"t": "order", "day": "2026-10-13", "buyer": "b1", "line": "regular", "kg": 4.0},
        {"t": "harvest", "batch": bid, "day": "2026-10-12", "kg": 3.0}]}]
    st, c, ref = _state(s, docs)
    from app import sim
    evs = sb.close_day(st, c, ref["buyers"], ref["households"], sim.plan(st, c, ref["buyers"]))
    assert not [e for e in evs if e["t"] == "harvest"]
    served = next(e for e in evs if e["t"] == "served")
    assert served["b2b_served"] == 3.0


def test_describe_formats():
    names, labels = {"b1": "Restaurant A"}, {"regular-2026-09-01": "Bed 3"}
    assert sb.describe({"t": "order", "day": "2026-10-16", "buyer": "b1", "line": "regular", "kg": 12}, names, labels) \
        == "ORDER · Restaurant A · regular · 12.0 kg · Fri 16 Oct"
    assert sb.describe({"t": "harvest", "batch": "regular-2026-09-01", "day": "2026-10-15", "kg": 20,
                        "big5_g": 640, "small5_g": 410}, names, labels) \
        == "HARVEST · Bed 3 · 20.0 kg · sample 640 g / 410 g"
    assert sb.describe({"t": "order", "day": "2026-10-16", "buyer": "zz", "line": "regular", "kg": 1}, names, labels) \
        == "ORDER · ⚠ unknown buyer zz · regular · 1.0 kg · Fri 16 Oct"


def test_form_loss_without_bed_expands_to_line():
    s = setup(beds=[{"line": "regular", "sown_on": "2026-09-01", "seedlings": 500},
                    {"line": "regular", "sown_on": "2026-09-08", "seedlings": 500}], start="2026-10-12")
    st, c, ref = _state(s)
    labels = {b.id: b.label for b in st.batches.values()}
    evs = sb.form_events({"kind": "loss", "line": "regular", "pct": 20, "cause": "pest"}, st, c, labels, {})
    assert len(evs) == 2 and all(e["t"] == "loss" for e in evs)


@pytest.mark.parametrize("raw", [
    {"kind": "order", "buyer": "b1", "line": "regular", "kg": 5, "day": "2026-10-12"},   # today, not tomorrow+
    {"kind": "order", "buyer": "b1", "line": "regular", "kg": 501, "day": "2026-10-13"},
    {"kind": "order", "buyer": "zz", "line": "regular", "kg": 5, "day": "2026-10-13"},
    {"kind": "order", "buyer": "b1", "line": "baby", "kg": 5, "day": "2026-10-13"},      # b1 buys regular only
    {"kind": "sow", "line": "regular", "seedlings": 0},
    {"kind": "harvest", "batch": "nope", "kg": 1},
    {"kind": "signal", "scope": "all", "effect_pct": 400, "date_from": "2026-10-12"},
])
def test_form_rejects(raw):
    s = setup(start="2026-10-12", buyers=[{"name": "Restaurant A", "type": "business", "line": "regular"}])
    st, c, ref = _state(s)
    with pytest.raises(ValueError):
        sb.form_events(raw, st, c, {}, {"b1": {"regular"}})


def test_assumed_harvest_does_not_count_as_logged_next_day():
    s = setup(start="2026-10-12",
              buyers=[{"name": "Restaurant A", "type": "business", "line": "regular", "usual_kg_per_week": 14}],
              beds=[{"line": "regular", "sown_on": "2026-09-01", "seedlings": 1000}])
    from app import sim
    st, c, ref = _state(s)
    day1 = sb.close_day(st, c, ref["buyers"], ref["households"], sim.plan(st, c, ref["buyers"]))
    assert [e for e in day1 if e["t"] == "harvest" and e.get("assumed")]
    st, c, ref = _state(s, [{"seq": 1, "kind": "day", "events": day1}])
    assert st.harvested == {}
    day2 = sb.close_day(st, c, ref["buyers"], ref["households"], sim.plan(st, c, ref["buyers"]))
    assert [e for e in day2 if e["t"] == "harvest"]


def test_close_day_skips_order_on_line_buyer_lacks():
    s = setup(start="2026-10-12", buyers=[{"name": "Restaurant A", "type": "business", "line": "regular"}])
    st, c, ref = _state(s, [{"seq": 1, "kind": "form", "events": [
        {"t": "order", "day": "2026-10-13", "buyer": "b1", "line": "baby", "kg": 2}]}])
    from app import sim
    evs = sb.close_day(st, c, ref["buyers"], ref["households"], sim.plan(st, c, ref["buyers"]))
    assert evs[-1]["t"] == "clock"


def test_stretch_g_defaults_and_validation():
    s = setup()
    assert {ln["id"]: ln["stretch_g"] for ln in s["crop"]["lines"]} == {"regular": 160, "baby": 80}
    bad = {**sb.default_setup()["crop"], "lines": [{"id": "r", "min_g": 100, "max_g": 140, "stretch_g": 130}]}
    with pytest.raises(ValidationError):
        sb.SetupIn.model_validate({**sb.default_setup(), "crop": bad})
    old = {**sb.default_setup()["crop"], "lines": [{"id": "r", "min_g": 100, "max_g": 140}]}
    assert sb.SetupIn.model_validate({**sb.default_setup(), "crop": old}).crop.lines[0].stretch_g is None
    c = crop_from_dict(sb.reference(s)["crops"][0])
    assert c.line("baby").top_g == 80 and c.line("baby").max_g == 70


def test_plan_sends_a_fair_share_when_short():
    s = setup(start="2026-10-26",
              buyers=[{"name": "Resto", "type": "business", "line": "baby", "usual_kg_per_week": 140}],
              beds=[{"line": "baby", "sown_on": "2026-09-28", "seedlings": 900}])
    st, c, ref = _state(s, [{"seq": 1, "kind": "form", "events": [
        {"t": "order", "day": "2026-10-27", "buyer": "b1", "line": "baby", "kg": 20.0}]}])
    from app import sim
    p = sim.plan(st, c, ref["buyers"])["baby"]
    assert 3 < p.send < 17 and p.ceiling == p.send
