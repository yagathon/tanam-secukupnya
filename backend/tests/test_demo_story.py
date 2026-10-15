"""The demo video's natural-loss moment: a pest spread over every bed shows up honestly as a shortfall
(tomorrow short, or shortfall ahead on Sow), so the farmer knows to tell buyers and top up from the market.
Natural losses are not the engine's job to hide; oversupply from human mismanagement is the story."""

from fastapi.testclient import TestClient

from app import gemini, main
from app.notes import LossReading, NoteReading

client = TestClient(main.app)


def test_a_pest_spread_over_the_beds_shows_up_as_a_shortfall(monkeypatch):
    client.post("/api/demo/reset")
    try:
        beds = [b for b in client.get("/api/beds").json()["lines"][0]["batches"]
                if b["stage"] == "bed" and b["plants_left"] > 0]
        assert len(beds) >= 3
        for b in beds:
            monkeypatch.setattr(gemini, "read_note", lambda *a, _b=b, **k: {"model": "fake", "reading": NoteReading(
                kind="loss", summary_en="pest", loss=LossReading(bed=_b["label"], pct=30, cause="caterpillars",
                                                                 cause_category="pest"))})
            n = client.post("/api/notes", json={"text": f"ulat {b['label']} 30%", "sender": "farmer"}).json()
            assert client.post(f"/api/notes/{n['id']}/accept").status_code == 200
        t = client.get("/api/today").json()["lines"][0]
        assert t["short_kg"] > 0 or t["sow"]["shortfall_ahead_kg"] > 0, t
    finally:
        client.post("/api/demo/reset")
