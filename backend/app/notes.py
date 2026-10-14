"""G1: a free-text Bahasa note → one proposed farm event (orders, harvest, sowing, loss, signal) or nothing.

This module holds everything about notes except the Gemini call: the schema the model fills, the
context it gets (aliases, bed labels, a day table), the sanitizer that turns a raw reading into a
safe proposal, the conversion of an accepted proposal into log events, and the eval scorer.

The model only *proposes*. Nothing reaches the farm state until a person accepts it, and the
sanitizer drops any id, bed, line or date the model could not have legitimately produced.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

KINDS = ("orders", "harvest", "sowing", "loss", "signal", "none")
SIGNAL_CAUSES = ("renovation", "closure", "event", "holiday", "school_calendar", "menu_change",
                 "low_traffic", "contract_change", "stock", "new_customers", "other")
LOSS_CAUSES = ("pest", "disease", "weather", "flood", "drought", "other")
CAUSES = tuple(dict.fromkeys(SIGNAL_CAUSES + LOSS_CAUSES))
ORDER_DAYS_AHEAD = 14
SIGNAL_DAYS_AHEAD = 182        # an open-ended signal runs to the end of the season
MAX_KG = 500.0

Cause = Literal[CAUSES]  # type: ignore[valid-type]


# --- what the model fills (flat: response schemas handle few nesting tricks) ---

class OrderReading(BaseModel):
    buyer: str = Field(description="buyer id from the context")
    line: str = Field(description='"regular" or "baby"')
    kg: float
    day: str = Field(description="delivery day YYYY-MM-DD from the days table; besok = tomorrow")


class HarvestReading(BaseModel):
    bed: str = Field(description='bed label from the context, e.g. "Bed 41"')
    kg: float = Field(description="kg harvested")
    big5_g: float | None = Field(description="the 5 biggest plants weighed together, grams; null if not given")
    small5_g: float | None = Field(description="the 5 smallest plants weighed together, grams; null if not given")


class SowingReading(BaseModel):
    line: str
    seedlings: int | None = Field(description="seedlings sown; null when postponed")
    postponed: bool = Field(description="true when today's sowing did not happen")
    reason: str = Field(description="short English reason when postponed, else empty")


class LossReading(BaseModel):
    bed: str = Field(description="bed label from the context")
    pct: float = Field(description="share of the plants still in that bed that are lost, 0–100")
    cause: str
    cause_category: Cause


class SignalReading(BaseModel):
    scope: str = Field(description='"all", "channel:B2B", "channel:B2C" or "buyer:<buyer id>"')
    line: str | None = Field(description="line id, or null when the note covers every line")
    effect_pct: float = Field(description="+20 = 20% more demand, -100 = stop entirely")
    date_from: str = Field(description="first affected day YYYY-MM-DD")
    date_to: str | None = Field(description="last affected day YYYY-MM-DD; null if open-ended")
    cause: str
    cause_category: Cause


class NoteReading(BaseModel):
    kind: Literal[KINDS]  # type: ignore[valid-type]
    orders: list[OrderReading] = Field(default_factory=list)
    harvest: HarvestReading | None = None
    sowing: SowingReading | None = None
    loss: LossReading | None = None
    signals: list[SignalReading] = Field(default_factory=list)
    summary_en: str = Field(description="one short English sentence: what the note says")


# --- context ---

def day_table(today: date, days: int = 35) -> list[dict]:
    """Coming days with plain labels, so the model looks dates up instead of computing them."""
    labels = {0: "today (hari ini)", 1: "tomorrow (besok)", 2: "day after tomorrow (lusa)"}
    return [{"date": (today + timedelta(days=i)).isoformat(), "weekday": (today + timedelta(days=i)).strftime("%A"),
             "label": labels.get(i, "")} for i in range(days)]


def context(today: date, buyers: list[dict], beds: list[dict], lines: list[str], usual: dict[str, float]) -> dict:
    """beds: [{"label", "line", "bed_day"}] for batches in the ground; usual: "buyer:line" → kg per order day."""
    return {
        "today": today.isoformat(), "weekday": today.strftime("%A"), "lines": lines,
        "buyers": [{"id": b["id"], "alias": b["alias"], "lines": sorted(b["lines"])} for b in buyers],
        "beds": beds, "usual_kg_per_order": usual, "days": day_table(today),
    }


# --- sanitize: model reading → storable proposal ---

def _day(s: str | None, lo: date, hi: date) -> date | None:
    try:
        d = date.fromisoformat(s) if s else None
    except ValueError:
        return None
    return d if d is not None and lo <= d <= hi else None


def _kg(x: float) -> float | None:
    return round(x, 2) if 0 < x <= MAX_KG else None


def sanitize(r: NoteReading, today: date, buyers: list[dict], beds: dict[str, str], lines: list[str],
             max_seedlings: int) -> tuple[dict, list[str]]:
    """Clamp a reading to known ids, beds (label → batch id) and sane ranges. Returns (proposal, dropped)."""
    dropped: list[str] = []
    out: dict = {"kind": r.kind, "summary_en": r.summary_en[:300], "orders": [], "harvest": None,
                 "sowing": None, "loss": None, "signals": []}
    blines = {b["id"]: set(b["lines"]) for b in buyers}
    if r.kind == "orders":
        for o in r.orders:
            d = _day(o.day, today + timedelta(days=1), today + timedelta(days=ORDER_DAYS_AHEAD))
            if o.buyer not in blines or o.line not in blines[o.buyer]:
                dropped.append(f"unknown buyer/line {o.buyer!r}/{o.line!r}")
            elif d is None or _kg(o.kg) is None:
                dropped.append(f"bad day or kg {o.day!r}/{o.kg!r}")
            else:
                out["orders"].append({"buyer": o.buyer, "line": o.line, "kg": _kg(o.kg), "day": d.isoformat()})
    elif r.kind == "harvest" and r.harvest:
        h = r.harvest
        if h.bed not in beds or _kg(h.kg) is None:
            dropped.append(f"unknown bed or bad kg {h.bed!r}/{h.kg!r}")
        else:
            big, small = h.big5_g, h.small5_g
            if big is not None and small is not None and not (big >= small > 0):
                dropped.append(f"sample needs big ≥ small > 0, got {big!r}/{small!r}")
                big = small = None
            if big is None or small is None:
                big = small = None
            out["harvest"] = {"bed": h.bed, "batch": beds[h.bed], "kg": _kg(h.kg), "big5_g": big, "small5_g": small}
    elif r.kind == "sowing" and r.sowing:
        s = r.sowing
        if s.line not in lines:
            dropped.append(f"unknown line {s.line!r}")
        elif s.postponed:
            out["sowing"] = {"line": s.line, "postponed": True, "seedlings": None, "reason": s.reason[:120]}
        elif s.seedlings is None or not 0 < s.seedlings <= max_seedlings:
            dropped.append(f"bad seedlings {s.seedlings!r}")
        else:
            out["sowing"] = {"line": s.line, "postponed": False, "seedlings": int(s.seedlings), "reason": ""}
    elif r.kind == "loss" and r.loss:
        lo = r.loss
        if lo.bed not in beds:
            dropped.append(f"unknown bed {lo.bed!r}")
        else:
            out["loss"] = {"bed": lo.bed, "batch": beds[lo.bed], "pct": max(0.0, min(100.0, round(lo.pct, 1))),
                           "cause": lo.cause[:120], "cause_category": lo.cause_category}
    elif r.kind == "signal":
        scopes = {"all", "channel:B2B", "channel:B2C"} | {f"buyer:{b}" for b in blines}
        for s in r.signals:
            hi = today + timedelta(days=SIGNAL_DAYS_AHEAD)
            d0 = _day(s.date_from, today, hi)
            d1 = _day(s.date_to, today, hi) if s.date_to else hi
            if s.scope not in scopes or (s.line is not None and s.line not in lines):
                dropped.append(f"unknown scope/line {s.scope!r}/{s.line!r}")
            elif d0 is None or d1 is None:
                dropped.append(f"bad dates {s.date_from!r}–{s.date_to!r}")
            else:
                out["signals"].append({
                    "scope": s.scope, "line": s.line, "effect_pct": max(-100.0, min(300.0, round(s.effect_pct, 1))),
                    "date_from": d0.isoformat(), "date_to": max(d0, d1).isoformat(), "open_ended": s.date_to is None,
                    "cause": s.cause[:120], "cause_category": s.cause_category})
    if r.kind != "none" and not (out["orders"] or out["harvest"] or out["sowing"] or out["loss"] or out["signals"]):
        out["kind"] = "none"
    return out, dropped


# --- accepted proposal → log events (see state.py for the event kinds) ---

def to_events(p: dict, today: date, next_sow: dict[str, date]) -> list[dict]:
    t = today.isoformat()
    if p["kind"] == "orders":
        return [{"t": "order", **o} for o in p["orders"]]
    if p["kind"] == "harvest":
        h = p["harvest"]
        ev = {"t": "harvest", "batch": h["batch"], "day": t, "kg": h["kg"]}
        return [{**ev, "big5_g": h["big5_g"], "small5_g": h["small5_g"]} if h["big5_g"] else ev]
    if p["kind"] == "sowing":
        s = p["sowing"]
        if s["postponed"]:
            return [{"t": "postpone", "line": s["line"], "day": next_sow[s["line"]].isoformat(), "reason": s["reason"]}]
        return [{"t": "sow", "line": s["line"], "day": t, "seedlings": s["seedlings"]}]
    if p["kind"] == "loss":
        lo = p["loss"]
        return [{"t": "loss", "batch": lo["batch"], "day": t, "pct": lo["pct"], "cause": lo["cause"]}]
    if p["kind"] == "signal":
        return [{"t": "signal", **{k: s[k] for k in ("scope", "line", "effect_pct", "date_from", "date_to", "cause")}}
                for s in p["signals"]]
    return []


# --- scoring (eval) ---

def bucket(pct: float) -> str:
    """Magnitude buckets for signals: the sign plus a coarse size."""
    if pct <= -100:
        return "stop"
    a = abs(pct)
    size = "zero" if a < 1 else "small" if a < 15 else "medium" if a <= 40 else "large"
    return size if size == "zero" else f"{'+' if pct > 0 else '-'}{size}"


def _close(a: float | None, b: float | None, rel: float, absolute: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= max(absolute, rel * abs(b))


def _fields(kind: str, e: dict, g: dict | None) -> dict[str, bool]:
    """Field → correct. With no reading to compare (g is None) every field is wrong, including ones
    whose expected value is null."""
    f = _compare(kind, e, g or {})
    return f if g is not None else dict.fromkeys(f, False)


def _compare(kind: str, e: dict, g: dict) -> dict[str, bool]:
    if kind == "orders":
        return {"buyer": e["buyer"] == g.get("buyer"), "line": e["line"] == g.get("line"),
                "kg": _close(g.get("kg"), e["kg"], 0.05, 0.1), "day": e["day"] == g.get("day")}
    if kind == "harvest":
        return {"bed": e["bed"] == g.get("bed"), "kg": _close(g.get("kg"), e["kg"], 0.05, 0.1),
                "sample": _close(g.get("big5_g"), e.get("big5_g"), 0.02, 5) and _close(g.get("small5_g"), e.get("small5_g"), 0.02, 5)}
    if kind == "sowing":
        return {"line": e["line"] == g.get("line"), "postponed": e["postponed"] == g.get("postponed"),
                "seedlings": e.get("seedlings") == g.get("seedlings")}
    if kind == "loss":
        return {"bed": e["bed"] == g.get("bed"), "pct": _close(g.get("pct"), e["pct"], 0, 10),
                "cause": e["cause_category"] == g.get("cause_category")}
    return {"scope": e["scope"] == g.get("scope"), "line": e.get("line") == g.get("line", "∅"),
            "direction": "effect_pct" in g and (e["effect_pct"] > 0) == (g["effect_pct"] > 0),
            "magnitude": "effect_pct" in g and bucket(e["effect_pct"]) == bucket(g["effect_pct"]),
            "period": e["date_from"] == g.get("date_from") and e["date_to"] == g.get("date_to"),
            "cause": e["cause_category"] == g.get("cause_category")}


LIST_KINDS = {"orders": "orders", "signal": "signals"}
ONE_KINDS = {"harvest": "harvest", "sowing": "sowing", "loss": "loss"}


def score(expected: dict, got: dict) -> dict:
    """Field-level comparison of one labeled note against one sanitized proposal.

    Returns {"kind_ok", "fields": {name: bool}, "extra"}; `extra` counts proposed items with no
    labeled counterpart (a false alarm the person would have to reject)."""
    kind = expected["kind"]
    res = {"kind_ok": kind == got["kind"], "fields": {}, "extra": 0}
    if kind in LIST_KINDS:
        k = LIST_KINDS[kind]
        pool = list(got.get(k) or []) if got["kind"] == kind else []
        for i, e in enumerate(expected[k]):
            best = max(pool, key=lambda g: sum(_fields(kind, e, g).values()), default=None)
            if best is not None:
                pool.remove(best)
            for f, v in _fields(kind, e, best).items():
                res["fields"][f"{i}.{f}"] = v
        res["extra"] = len(pool)
    elif kind in ONE_KINDS:
        g = got.get(ONE_KINDS[kind]) if got["kind"] == kind else None
        res["fields"] = _fields(kind, expected[ONE_KINDS[kind]], g)
    else:
        res["extra"] = len(got.get("orders") or []) + len(got.get("signals") or []) + sum(
            1 for k in ONE_KINDS.values() if got.get(k))
    return res
