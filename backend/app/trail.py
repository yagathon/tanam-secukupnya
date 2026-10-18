"""The decision trail: for every closed day, what the engine decided that morning (before any of the
day's entries) and what came in.

Replays the sandbox log once, planning at each day boundary; cached per workspace and continued
from the last day when the log only grew (a setup edit or a clear rebuilds it)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app import farm, sandbox, sim
from app.state import FarmState, apply, current_crop, initial
from app.store import Store


@dataclass
class _Cache:
    rev: str | None
    prints: list[str]                # content fingerprint per replayed log entry
    state: FarmState
    rows: list[dict] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    entries: list[dict] = field(default_factory=list)   # today's entries, one per log doc: {id, lines}
    ref_seen: int = 0
    morning: dict | None = None      # today's plan, taken before the day's first entry


_cache: dict[str, _Cache] = {}
_LOGGED = ("order", "harvest", "sow", "postpone", "loss")   # demo day-doc events a farmer would have entered


def _row(st, crop, buyers, inputs, ref, live) -> dict:
    plans = sim.plan(st, crop, buyers)
    lines = {}
    for line, p in plans.items():
        r0 = p.needs.rows[0] if p.needs.rows else {"low": 0, "high": 0}
        lines[line] = {"low": r0["low"], "high": r0["high"], "ready": round(p.available_tomorrow, 2),
                       "ceiling": round(p.ceiling, 2), "send": round(p.send, 2), "short": None,
                       "sow_day": p.sow.day.isoformat() if p.sow.day else None, "sow_seedlings": p.sow.seedlings}
    return {"day": st.today.isoformat(), "live": live, "lines": lines, "inputs": inputs, "ref": ref}


def build(ws: Store) -> dict:
    meta, docs = ws.meta(), sorted(ws.list("events"), key=lambda d: d["seq"])
    c = farm.crop(ws)
    buyers = ws.list("buyers")
    names = {b["id"]: b["alias"] for b in buyers} | {h["id"]: h["alias"] for h in ws.list("households")}
    demo = not meta.get("sandbox")       # the demo farm logs only by its simulated day docs
    hit = _cache.get(ws.uid)
    prints = [farm.doc_print(d) for d in docs]
    if hit is None or hit.rev != meta.get("rev") or prints[:len(hit.prints)] != hit.prints:
        st = initial({"batches": ws.list("batches"), "history": ws.list("history")}, meta)
        hit = _Cache(meta.get("rev"), [], st)
    start = len(hit.prints)
    st = hit.state
    for doc, fp in zip(docs[start:], prints[start:], strict=True):
        labels = {b.id: b.label for b in st.batches.values()}
        if hit.morning is None:
            hit.morning = _row(st, current_crop(st, c), buyers, [], [], False)
        if doc["kind"] == "day":
            row = {**hit.morning, "inputs": list(hit.pending), "ref": [_ref_line(e) for e in st.ref_log[hit.ref_seen:]]}
            hit.ref_seen, hit.pending, hit.entries, hit.morning = len(st.ref_log), [], [], None
        else:
            hit.entries.append({"id": doc["id"], "lines": []})
        for ev in doc["events"]:
            if doc["kind"] != "day":
                hit.pending.append(sandbox.describe(ev, names, labels))
                hit.entries[-1]["lines"].append(hit.pending[-1])
            elif demo and ev["t"] in _LOGGED:
                row["inputs"].append(sandbox.describe(ev, names, labels))
            if doc["kind"] == "day" and ev["t"] == "served":
                row["lines"][ev["line"]]["short"] = round(ev["b2b_ordered"] + ev["hh_ordered"]
                                                          - ev["b2b_served"] - ev["hh_served"], 2)
            apply(st, c, ev)
        if doc["kind"] == "day":
            hit.rows.append(row)
        hit.prints.append(fp)
    _cache[ws.uid] = hit
    live = _row(st, current_crop(st, c), buyers, list(hit.pending),
                [_ref_line(e) for e in st.ref_log[hit.ref_seen:]], True)
    live["entries"] = [{**e, "lines": list(e["lines"])} for e in hit.entries]
    return {"rows": [live] + hit.rows[::-1], "replayed_from": start}


def _ref_line(e: dict) -> str:
    if e.get("reset"):
        return "reference reset to the starting curve"
    if e["node_days"]:
        return f"{e['bed']} sample ×{e['ratio']:.2f} → nodes at day {', '.join(str(int(x)) for x in e['node_days'])}"
    return f"{e['bed']} sample ×{e['ratio']:.2f} (reference held)"
