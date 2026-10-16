from app.store import SANDBOX, JsonStore


def test_demo_reset_keeps_sandbox_and_sandbox_reset_keeps_demo():
    ws = JsonStore().for_user("t-reset")
    ws.put("notes", {"id": "n1", "text": "x"})
    ws.put("sandbox_events", {"id": "e1", "seq": 1, "events": []})
    ws.reset()
    assert ws.list("notes") == [] and len(ws.list("sandbox_events")) == 1
    ws.put("notes", {"id": "n1", "text": "x"})
    ws.reset(SANDBOX)
    assert ws.list("sandbox_events") == [] and len(ws.list("notes")) == 1
