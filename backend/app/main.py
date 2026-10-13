"""FastAPI app: every route under /api (Firebase Hosting rewrites /api/** to Cloud Run).

Gemini routes (/notes) are cached by input and capped per day, so a public demo URL cannot run up
the bill. Auth (Firebase anonymous ID token) is still to come.
"""

from __future__ import annotations

import hashlib
import os
import threading
from datetime import date

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import gemini, notes, service
from app.store import JsonStore, Store

store: Store = JsonStore()
api = APIRouter(prefix="/api")


class PlanRequest(BaseModel):
    horizon_weeks: int = Field(service.HORIZON_WEEKS, ge=1, le=26)


class NoteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    sender: str = Field(min_length=1, max_length=40)


class ScenarioRequest(BaseModel):
    crop: str
    week: date
    harvest_pct: float = Field(100, ge=0, le=150)


@api.get("/health")
def health() -> dict:
    return {"ok": True}


@api.get("/state")
def state() -> dict:
    return {
        "today": service.today(store),
        "synthetic": store.meta().get("synthetic", True),
        **{c: store.list(c) for c in ("crops", "farmers", "partners", "households", "batches", "signals", "notes")},
    }


@api.post("/forecast/run")
def forecast_run(req: PlanRequest = PlanRequest()) -> dict:
    return {"today": service.today(store), "series": service.forecast_view(store, req.horizon_weeks)}


@api.post("/plan/run")
def plan_run(req: PlanRequest = PlanRequest()) -> dict:
    return {"today": service.today(store), "plans": service.run_plan(store, req.horizon_weeks)}


@api.post("/scenario")
def scenario(req: ScenarioRequest) -> dict:
    if req.crop not in service.crops(store):
        raise HTTPException(404, f"unknown crop {req.crop!r}")
    return service.run_scenario(store, req.crop, req.week, req.harvest_pct)


DAILY_CAP = int(os.environ.get("GEMINI_DAILY_CAP", "300"))
_g1_cache: dict[str, dict] = {}
_calls: dict[str, int] = {}
_calls_lock = threading.Lock()


def _spend_one_call() -> None:
    """Per-instance daily cap on Gemini calls (Cloud Run max 2 instances → at most 2× this)."""
    day = date.today().isoformat()
    with _calls_lock:
        n = _calls.get(day, 0)
        if n >= DAILY_CAP:
            raise HTTPException(429, "Daily Gemini budget for this demo is used up; try again tomorrow.")
        _calls.clear()
        _calls[day] = n + 1


def _state_for_notes() -> dict:
    return {"today": service.today(store).isoformat(),
            **{c: store.list(c) for c in ("crops", "farmers", "partners", "households")}}


@api.post("/notes")
def read_note(req: NoteRequest) -> dict:
    """G1: a note → proposed signals (not yet accepted) or a harvest issue, stored with the note."""
    state = _state_for_notes()
    senders = {p["id"] for p in state["partners"]} | {f["id"] for f in state["farmers"]} | {"operator"}
    if req.sender not in senders:
        raise HTTPException(422, f"unknown sender {req.sender!r}")
    text = req.text.strip()
    key = hashlib.sha256(f"{state['today']}|{req.sender}|{text}".encode()).hexdigest()
    hit = _g1_cache.get(key)
    cached = hit is not None
    if hit is None:
        _spend_one_call()
        try:
            out = gemini.read_note(text, req.sender, state["today"], notes.context(state, service.recent_avg_kg(store)))
        except Exception as e:
            raise HTTPException(502, f"Gemini could not read the note ({type(e).__name__}).") from e
        proposal, dropped = notes.sanitize(out["reading"], state)
        hit = _g1_cache[key] = {"proposal": proposal, "dropped": dropped, "model": out["model"]}
    p = hit["proposal"]
    note = store.put("notes", {"text": text, "sender": req.sender, "received_on": state["today"], "kind": p["kind"],
                               "summary_en": p["summary_en"], "harvest_issue": p["harvest_issue"],
                               "status": "proposed" if p["kind"] != "none" else "no_action",
                               "dropped": hit["dropped"], "model": hit["model"], "cached": cached})
    sigs = [store.put("signals", {**s, "week_to": notes.open_end(s["week_from"], s["week_to"]), "open_ended": s["week_to"] is None,
                                  "source": "note", "note_id": note["id"], "accepted": False})
            for s in p["signals"]]
    return {**note, "signals": sigs}


def _decide(collection: str, id: str, accepted: bool) -> dict:
    doc = store.get(collection, id)
    if doc is None:
        raise HTTPException(404, f"no such {collection[:-1]} {id!r}")
    return store.put(collection, {**doc, "accepted": accepted, "status": "accepted" if accepted else "rejected"})


@api.post("/signals/{id}/accept")
def accept_signal(id: str) -> dict:
    return _decide("signals", id, True)


@api.post("/signals/{id}/reject")
def reject_signal(id: str) -> dict:
    return _decide("signals", id, False)


@api.post("/notes/{id}/accept")
def accept_note(id: str) -> dict:
    """Accept a note's harvest issue (signals are accepted one by one)."""
    return _decide("notes", id, True)


@api.post("/notes/{id}/reject")
def reject_note(id: str) -> dict:
    return _decide("notes", id, False)


@api.post("/demo/reset")
def demo_reset() -> dict:
    store.reset()
    return {"ok": True}


@api.get("/gemini/ping")
def gemini_ping() -> dict:
    return gemini.ping()


app = FastAPI(title="Tanam Secukupnya", version="0.1.0")
app.include_router(api)
