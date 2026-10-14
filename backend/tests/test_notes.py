from datetime import date

from app import notes
from app.notes import (
    HarvestReading,
    LossReading,
    NoteReading,
    OrderReading,
    SignalReading,
    SowingReading,
    sanitize,
    score,
    to_events,
)

TODAY = date(2026, 10, 12)  # a Monday
BUYERS = [{"id": "resto_a", "alias": "Restaurant A", "lines": {"regular": {}}},
          {"id": "cafe_e", "alias": "Cafe E", "lines": {"regular": {}, "baby": {}}}]
BEDS = {"Bed 41": "regular-2026-09-10"}
LINES = ["regular", "baby"]


def clean(r: NoteReading) -> tuple[dict, list[str]]:
    return sanitize(r, TODAY, BUYERS, BEDS, LINES, 3000)


def test_day_table_labels_tomorrow_and_lusa():
    t = notes.day_table(TODAY, 3)
    assert [(d["date"], d["label"]) for d in t][1:] == [("2026-10-13", "tomorrow (besok)"),
                                                        ("2026-10-14", "day after tomorrow (lusa)")]


def test_orders_keep_known_buyers_lines_and_days_only():
    r = NoteReading(kind="orders", summary_en="x", orders=[
        OrderReading(buyer="resto_a", line="regular", kg=8, day="2026-10-13"),
        OrderReading(buyer="resto_a", line="baby", kg=2, day="2026-10-13"),      # resto_a takes no baby
        OrderReading(buyer="ghost", line="regular", kg=2, day="2026-10-13"),
        OrderReading(buyer="cafe_e", line="baby", kg=2, day="2026-10-12"),       # today: too late
        OrderReading(buyer="cafe_e", line="baby", kg=2, day="2026-10-27"),       # beyond 14 days
        OrderReading(buyer="cafe_e", line="baby", kg=0, day="2026-10-14")])
    p, dropped = clean(r)
    assert p["orders"] == [{"buyer": "resto_a", "line": "regular", "kg": 8, "day": "2026-10-13"}]
    assert len(dropped) == 5


def test_a_reading_with_nothing_left_becomes_none():
    p, dropped = clean(NoteReading(kind="harvest", summary_en="x",
                                   harvest=HarvestReading(bed="Bed 99", kg=3, big5_g=None, small5_g=None)))
    assert p["kind"] == "none" and dropped


def test_harvest_maps_the_bed_label_to_its_batch_and_checks_the_sample():
    ok, _ = clean(NoteReading(kind="harvest", summary_en="x",
                              harvest=HarvestReading(bed="Bed 41", kg=12.5, big5_g=600, small5_g=300)))
    assert ok["harvest"] == {"bed": "Bed 41", "batch": "regular-2026-09-10", "kg": 12.5, "big5_g": 600, "small5_g": 300}
    bad, dropped = clean(NoteReading(kind="harvest", summary_en="x",
                                     harvest=HarvestReading(bed="Bed 41", kg=12.5, big5_g=300, small5_g=600)))
    assert bad["harvest"]["big5_g"] is None and dropped


def test_sowing_postponed_or_counted():
    p, _ = clean(NoteReading(kind="sowing", summary_en="x",
                             sowing=SowingReading(line="regular", seedlings=None, postponed=True, reason="rain")))
    assert p["sowing"] == {"line": "regular", "postponed": True, "seedlings": None, "reason": "rain"}
    p, dropped = clean(NoteReading(kind="sowing", summary_en="x",
                                   sowing=SowingReading(line="regular", seedlings=5000, postponed=False, reason="")))
    assert p["kind"] == "none" and dropped


def test_loss_pct_is_clamped():
    p, _ = clean(NoteReading(kind="loss", summary_en="x",
                             loss=LossReading(bed="Bed 41", pct=130, cause="ulat", cause_category="pest")))
    assert p["loss"]["pct"] == 100 and p["loss"]["batch"] == "regular-2026-09-10"


def test_signal_scope_and_open_end():
    r = NoteReading(kind="signal", summary_en="x", signals=[
        SignalReading(scope="buyer:resto_a", line=None, effect_pct=-100, date_from="2026-10-19", date_to="2026-10-25",
                      cause="renovasi", cause_category="renovation"),
        SignalReading(scope="channel:B2B", line="regular", effect_pct=20, date_from="2026-10-13", date_to=None,
                      cause="x", cause_category="other"),
        SignalReading(scope="buyer:ghost", line=None, effect_pct=10, date_from="2026-10-13", date_to=None,
                      cause="x", cause_category="other")])
    p, dropped = clean(r)
    assert [s["scope"] for s in p["signals"]] == ["buyer:resto_a", "channel:B2B"]
    assert p["signals"][1]["open_ended"] and p["signals"][1]["date_to"] == "2027-04-12"
    assert len(dropped) == 1


def test_to_events_per_kind():
    nxt = {"regular": date(2026, 10, 15), "baby": date(2026, 10, 15)}
    sow = {"kind": "sowing", "sowing": {"line": "regular", "postponed": True, "seedlings": None, "reason": "rain"}}
    assert to_events(sow, TODAY, nxt) == [{"t": "postpone", "line": "regular", "day": "2026-10-15", "reason": "rain"}]
    hv = {"kind": "harvest", "harvest": {"bed": "Bed 41", "batch": "b1", "kg": 3.0, "big5_g": None, "small5_g": None}}
    assert to_events(hv, TODAY, nxt) == [{"t": "harvest", "batch": "b1", "day": "2026-10-12", "kg": 3.0}]
    assert to_events({"kind": "none"}, TODAY, nxt) == []


def test_score_matches_list_items_and_counts_extras():
    exp = {"kind": "orders", "orders": [{"buyer": "resto_a", "line": "regular", "kg": 8, "day": "2026-10-13"}]}
    got = {"kind": "orders", "orders": [{"buyer": "cafe_e", "line": "baby", "kg": 1, "day": "2026-10-13"},
                                        {"buyer": "resto_a", "line": "regular", "kg": 8.2, "day": "2026-10-13"}]}
    s = score(exp, got)
    assert s["kind_ok"] and all(s["fields"].values()) and s["extra"] == 1


def test_score_none_counts_any_proposal_as_extra():
    s = score({"kind": "none"}, {"kind": "signal", "signals": [{}], "orders": []})
    assert not s["kind_ok"] and s["extra"] == 1


def test_a_missing_reading_gets_no_field_right():
    exp = {"kind": "sowing", "sowing": {"line": "regular", "postponed": True, "seedlings": None}}
    s = score(exp, {"kind": "none"})
    assert not s["kind_ok"] and not any(s["fields"].values())


def test_bucket():
    assert [notes.bucket(x) for x in (-100, -30, 10, 0.5, 60)] == ["stop", "-medium", "+small", "zero", "+large"]
