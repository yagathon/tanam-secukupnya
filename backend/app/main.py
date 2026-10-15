"""FastAPI app: every route under /api (Firebase Hosting rewrites /api/** to Cloud Run).

Gemini (/notes, /today/why) is cached by input and capped per day, so a public demo URL cannot run up the bill.
Every route but /health needs a Firebase anonymous ID token; its uid scopes the visitor's workspace
(notes and the event log), so visitors never see or overwrite each other's farm.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import date

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from app import farm, gemini, notes, sandbox, trail
from app.auth import current_uid
from app.store import Store, make_store

store: Store = make_store()
public = APIRouter(prefix="/api")
api = APIRouter(prefix="/api")
sbx = APIRouter(prefix="/api/sandbox")


def workspace(request: Request, uid: str = Depends(current_uid)) -> Store:
    """The demo farm, or under /api/sandbox/ the visitor's own sandbox (same handlers, other reference)."""
    ws = store.for_user(uid)
    return sandbox.open_sandbox(ws) if request.url.path.startswith("/api/sandbox/") else ws


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
            "sandbox": ws.meta().get("sandbox", False),
            "crop": ws.list("crops")[0], "buyers": ws.list("buyers"), "households": ws.list("households"),
            "senders": senders(ws), "reference": farm.reference(ws)}


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
    try:
        return farm.next_day(ws, req.from_day, req.days)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


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
    events = notes.to_events(proposal, inp["today"], inp["next_sow"]) if proposal["kind"] != "none" else []
    names = {b["id"]: b["alias"] for b in ws.list("buyers")}
    labels = {bid: lbl for lbl, bid in inp["beds"].items()}
    return ws.put("notes", {"preview": [sandbox.describe(e, names, labels) for e in events], "preview_events": events,
                            "text": text, "sender": req.sender, "received_on": today_iso, "proposal": proposal,
                            "kind": proposal["kind"], "summary_en": proposal["summary_en"],
                            "status": "proposed" if proposal["kind"] != "none" else "no_action",
                            "dropped": dropped, "model": hit["model"], "cached": cached})


_g5_cache: dict[str, dict] = {}


@api.post("/today/why")
def why(ws: Store = Depends(workspace)) -> dict:
    """G5: Gemini narrates today's numbers from the engine's own JSON (computes nothing)."""
    t, tm, sw = farm.today(ws), farm.tomorrow(ws), farm.sow(ws)
    t = {k: v for k, v in t.items() if k != "pending"}
    # keyed by the numbers themselves, so two visitors on the same farm state share one answer
    key = hashlib.sha256(json.dumps([t, tm, sw], sort_keys=True, default=str).encode()).hexdigest()
    if key in _g5_cache:
        return {**_g5_cache[key], "cached": True}
    _spend_one_call()
    try:
        out = gemini.explain(t, tm, sw)
    except Exception as e:
        raise HTTPException(502, f"Gemini could not explain the day ({type(e).__name__}).") from e
    if not out["text"]:
        raise HTTPException(502, "Gemini returned an empty explanation; try again.")
    _g5_cache[key] = out
    return {**out, "cached": False}

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
    if not farm.append(ws, inp["seq"], {"kind": "note", "note_id": id, "events": events}):
        raise HTTPException(409, "the farm changed while accepting this note; try again")
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


# --- sandbox: the visitor's own farm, entered by hand ---

for _path, _fn, _methods in [("/state", state, ["GET"]), ("/today", today, ["GET"]), ("/beds", beds, ["GET"]),
                             ("/tomorrow", tomorrow, ["GET"]), ("/sow", sow, ["GET"]), ("/demand", demand, ["GET"]),
                             ("/day/next", day_next, ["POST"]), ("/notes", read_note, ["POST"]),
                             ("/notes/{id}/accept", accept_note, ["POST"]),
                             ("/notes/{id}/reject", reject_note, ["POST"]), ("/today/why", why, ["POST"])]:
    sbx.add_api_route(_path, _fn, methods=_methods)


class EventRequest(BaseModel):
    form: dict
    seq: int = Field(ge=1)


def _sandbox_ws(ws: Store) -> sandbox.SandboxStore:
    if not isinstance(ws, sandbox.SandboxStore):
        raise HTTPException(404)
    return ws


def _names(ws: Store) -> dict[str, str]:
    return {b["id"]: b["alias"] for b in ws.list("buyers")} | {h["id"]: h["alias"] for h in ws.list("households")}


@sbx.get("/setup")
def get_setup(ws: Store = Depends(workspace)) -> dict:
    ws = _sandbox_ws(ws)
    return {"saved": ws.saved, "setup": ws.setup, "locked_start": bool(ws.list("events"))}


@sbx.put("/setup")
def put_setup(body: dict, ws: Store = Depends(workspace)) -> dict:
    ws = _sandbox_ws(ws)
    docs = ws.list("events")
    try:
        body = sandbox.keep_ids(body, ws.setup if ws.saved else None, docs)
        new = sandbox.SetupIn.model_validate(body).model_dump(mode="json")
    except ValidationError as e:
        raise HTTPException(422, "; ".join(err["msg"] for err in e.errors())) from e
    if docs and new["start"] != ws.setup["start"]:
        raise HTTPException(422, "the start date is locked once days are logged; clear the sandbox first")
    nws = sandbox.SandboxStore(ws.base, new)
    try:
        farm.replay_check(nws)                                      # the whole log, replayed on the new setup
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"the logged days do not fit this setup ({e}); clear the sandbox or undo the change") from e
    stranded = sandbox.orphan_orders(farm.load(nws).state, sandbox.buyer_lines(nws))
    if stranded:
        raise HTTPException(422, f"orders still to come would lose their buyer or line ({', '.join(stranded)}); "
                                 "keep that buyer's line until those days pass, or clear the sandbox")
    ws.base.put("sandbox_setup", sandbox.setup_doc(new))
    return {"saved": True, "setup": new, "locked_start": bool(docs)}


@sbx.post("/events")
def post_events(req: EventRequest, ws: Store = Depends(workspace)) -> dict:
    ws = _sandbox_ws(ws)
    if not ws.saved:
        raise HTTPException(409, "save the setup first")
    v = farm.load(ws)
    labels = {b.id: b.label for b in v.state.batches.values()}
    try:
        events = sandbox.form_events(req.form, v.state, v.crop, labels, sandbox.buyer_lines(ws))
        farm.check_events(ws, events)
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(422, str(e)) from e
    if req.seq != v.log_key[1] + 1 or not farm.append(ws, req.seq, {"kind": "form", "events": events}):
        raise HTTPException(409, "the sandbox changed meanwhile; reload and try again")
    names = _names(ws)
    return {"events": events, "lines": [sandbox.describe(e, names, labels) for e in events]}


@sbx.get("/trail")
def get_trail(ws: Store = Depends(workspace)) -> dict:
    return trail.build(_sandbox_ws(ws))


@sbx.post("/clear")
def clear(ws: Store = Depends(workspace)) -> dict:
    _sandbox_ws(ws).reset(("sandbox_events", "sandbox_notes"))
    return {"ok": True}


app = FastAPI(title="Tanam Secukupnya", version="0.2.0")
app.include_router(public)
app.include_router(api)
app.include_router(sbx)
