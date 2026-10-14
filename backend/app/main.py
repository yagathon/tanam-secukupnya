"""FastAPI app: every route under /api (Firebase Hosting rewrites /api/** to Cloud Run).

Gemini (/notes) is cached by input and capped per day, so a public demo URL cannot run up the bill.
Every route but /health needs a Firebase anonymous ID token; its uid scopes the visitor's workspace
(notes and the event log), so visitors never see or overwrite each other's farm.
"""

from __future__ import annotations

import hashlib
import os
import threading
from datetime import date

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import farm, gemini, notes
from app.auth import current_uid
from app.store import Store, make_store

store: Store = make_store()
public = APIRouter(prefix="/api")
api = APIRouter(prefix="/api")


def workspace(uid: str = Depends(current_uid)) -> Store:
    return store.for_user(uid)


class NoteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    sender: str = Field(min_length=1, max_length=40)


class NextDayRequest(BaseModel):
    from_day: date
    days: int = Field(1, ge=1, le=14)


@public.get("/health")
def health() -> dict:
    return {"ok": True}


@api.get("/state")
def state(ws: Store = Depends(workspace)) -> dict:
    v = farm.load(ws)
    return {"today": v.state.today.isoformat(), "synthetic": ws.meta().get("synthetic", True),
            "crop": ws.list("crops")[0], "buyers": ws.list("buyers"), "households": ws.list("households"),
            "senders": senders(ws)}


@api.get("/today")
def today(ws: Store = Depends(workspace)) -> dict:
    return farm.today(ws)


@api.get("/beds")
def beds(ws: Store = Depends(workspace)) -> dict:
    return farm.beds(ws)


@api.get("/tomorrow")
def tomorrow(ws: Store = Depends(workspace)) -> dict:
    return farm.tomorrow(ws)


@api.get("/sow")
def sow(ws: Store = Depends(workspace)) -> dict:
    return farm.sow(ws)


@api.get("/demand")
def demand(ws: Store = Depends(workspace)) -> dict:
    return farm.demand(ws)


@api.get("/season")
def season(uid: str = Depends(current_uid)) -> dict:
    return farm.season()


@api.post("/day/next")
def day_next(req: NextDayRequest, ws: Store = Depends(workspace)) -> dict:
    return farm.next_day(ws, req.from_day, req.days)


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


def senders(ws: Store) -> list[dict]:
    return ([{"id": "farmer", "alias": "Farmer"}, {"id": "operator", "alias": "Operator"}]
            + [{"id": b["id"], "alias": b["alias"]} for b in ws.list("buyers")])


@api.post("/notes")
def read_note(req: NoteRequest, ws: Store = Depends(workspace)) -> dict:
    """G1: a note → one proposed event (not applied until accepted), stored with the note."""
    if req.sender not in {s["id"] for s in senders(ws)}:
        raise HTTPException(422, f"unknown sender {req.sender!r}")
    inp = farm.note_inputs(ws)
    today_iso = inp["today"].isoformat()
    text = req.text.strip()
    # the context (beds, usual kg) changes as the visitor's farm moves, so it is part of the key
    key = hashlib.sha256(f"{today_iso}|{req.sender}|{text}|{inp['ctx']}".encode()).hexdigest()
    hit = _g1_cache.get(key)
    cached = hit is not None
    if hit is None:
        _spend_one_call()
        try:
            out = gemini.read_note(text, req.sender, today_iso, inp["ctx"])
        except Exception as e:
            raise HTTPException(502, f"Gemini could not read the note ({type(e).__name__}).") from e
        hit = _g1_cache[key] = {"reading": out["reading"], "model": out["model"]}
    proposal, dropped = notes.sanitize(hit["reading"], inp["today"], ws.list("buyers"), inp["beds"], inp["lines"],
                                       inp["max_seedlings"])
    return ws.put("notes", {"text": text, "sender": req.sender, "received_on": today_iso, "proposal": proposal,
                            "kind": proposal["kind"], "summary_en": proposal["summary_en"],
                            "status": "proposed" if proposal["kind"] != "none" else "no_action",
                            "dropped": dropped, "model": hit["model"], "cached": cached})


def _note(ws: Store, id: str) -> dict:
    doc = ws.get("notes", id)
    if doc is None:
        raise HTTPException(404, f"no such note {id!r}")
    if doc["status"] != "proposed":
        raise HTTPException(409, f"note is already {doc['status']}")
    return doc


@api.post("/notes/{id}/accept")
def accept_note(id: str, ws: Store = Depends(workspace)) -> dict:
    """Turn the note's proposal into log events, dated the visitor's today."""
    doc = _note(ws, id)
    inp = farm.note_inputs(ws)
    if doc["received_on"] != inp["today"].isoformat():
        raise HTTPException(409, "the farm has moved on since this note was read; read it again")
    events = notes.to_events(doc["proposal"], inp["today"], inp["next_sow"])
    try:
        farm.check_events(ws, events)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"cannot apply this note ({e})") from e
    ws.put("events", {"seq": farm.next_seq(ws), "kind": "note", "note_id": id, "events": events})
    return ws.put("notes", {**doc, "status": "accepted", "events": events})


@api.post("/notes/{id}/reject")
def reject_note(id: str, ws: Store = Depends(workspace)) -> dict:
    return ws.put("notes", {**_note(ws, id), "status": "rejected"})


@api.post("/demo/reset")
def demo_reset(ws: Store = Depends(workspace)) -> dict:
    ws.reset()
    return {"ok": True}


@api.get("/gemini/ping")
def gemini_ping(uid: str = Depends(current_uid)) -> dict:
    return gemini.ping()


app = FastAPI(title="Tanam Secukupnya", version="0.2.0")
app.include_router(public)
app.include_router(api)
