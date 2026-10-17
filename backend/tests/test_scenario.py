"""scripts/scenario.py: the year scenario makes a sheet that reads back and plays into a sandbox."""

import sys
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app import sandbox as sb

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import scenario  # noqa: E402


def test_year_sheet_reads_back_with_its_stories(tmp_path):
    out = tmp_path / "year.xlsx"
    scenario.make(out)
    sc = scenario.load(out)
    rows = sc["rows"]
    assert sc["setup"]["start"] == "2026-10-17" and len(sc["setup"]["buyers"]) == 2
    assert rows[0]["date"] == "2026-10-17" and rows[-1]["date"] < "2027-10-17"
    kinds = {r["kind"] for r in rows}
    assert kinds == {"order", "sow", "loss", "signal", "postpone"}
    lebaran = [r for r in rows if r["kind"] == "order" and r["buyer"] == "Resto WKS"
               and "2027-03-08" <= r["for_day"] <= "2027-03-14"]
    assert lebaran and all(r["kg"] == 0 for r in lebaran)
    assert all(date.fromisoformat(r["for_day"]).weekday() in (5, 6) for r in rows if r.get("buyer") == "Retails")


def test_play_logs_the_rows_day_by_day_and_resumes(tmp_path):
    out = tmp_path / "s.xlsx"
    scenario.make(out, days=40)
    sc = scenario.load(out)
    main.store.for_user("local").reset(sb.SANDBOX)
    api = scenario.Http("http://testserver", TestClient(main.app))
    try:
        first = scenario.play(api, sc, reset=True, days=10, say=lambda *_: None)
        assert first["days"] == 10 and first["today"] == "2026-10-27" and first["skipped"] == 0
        rest = scenario.play(api, sc, say=lambda *_: None)
        assert rest["today"] == "2026-11-25" and rest["skipped"] == 0
        logged = [e for d in main.store.for_user("local").list("sandbox_events") for e in d.get("events", [])]
        assert {e["t"] for e in logged} >= {"order", "sow"}
    finally:
        main.store.for_user("local").reset(sb.SANDBOX)
