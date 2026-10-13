"""G1: a free-text Bahasa note → proposed demand signals or a harvest issue (or nothing).

This module holds everything about notes that is not the Gemini call itself: the output schema
the model must fill, the context it gets (aliases, the coming Mondays), the sanitizer that turns
a raw model reading into something safe to store, and the field-level scorer used by the eval.

The model only *proposes*. Nothing it returns reaches the forecast until a person accepts it, and
the sanitizer drops any id, crop or date it could not have legitimately produced.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

DEMAND_CAUSES = ("renovation", "closure", "event", "holiday", "school_calendar", "menu_change",
                 "low_traffic", "contract_change", "stock", "new_customers", "other")
HARVEST_CAUSES = ("pest", "disease", "weather", "flood", "drought", "seed_quality", "other")
CAUSES = tuple(dict.fromkeys(DEMAND_CAUSES + HARVEST_CAUSES))
KINDS = ("signals", "harvest_issue", "none")
HORIZON_WEEKS = 26  # an open-ended signal ("mulai minggu depan") runs to the planning horizon

Cause = Literal[CAUSES]  # type: ignore[valid-type]


# --- what the model fills (kept flat: response schemas handle few nesting tricks) ---

class SignalReading(BaseModel):
    scope: str = Field(description='"all", "channel:B2B", "channel:B2C" or "partner:<partner id>"')
    crop: str | None = Field(description="crop id, or null when the note covers every crop")
    effect_pct: float = Field(description="+20 = 20% more demand, -100 = stop entirely")
    week_from: str = Field(description="Monday (YYYY-MM-DD) of the first affected week")
    week_to: str | None = Field(description="Monday of the last affected week; null if open-ended")
    cause: str = Field(description="short English phrase for why, from the note")
    cause_category: Cause


class HarvestReading(BaseModel):
    farmer_id: str
    crop: str
    loss_pct: float = Field(description="share of the expected harvest lost, 0–100")
    delay_days: int = Field(0, description="days the harvest is pushed back; 0 if not delayed")
    harvest_week: str | None = Field(description="Monday of the affected harvest week, if stated")
    cause: str
    cause_category: Cause


class NoteReading(BaseModel):
    kind: Literal[KINDS]  # type: ignore[valid-type]
    signals: list[SignalReading] = Field(default_factory=list)
    harvest_issue: HarvestReading | None = None
    summary_en: str = Field(description="one short English sentence: what the note says")


# --- context ---

def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_table(today: date, weeks: int = 16) -> list[dict]:
    """The coming Mondays with plain labels, so the model looks dates up instead of computing them."""
    m0 = monday(today)
    labels = {0: "this week (minggu ini)", 1: "next week (minggu depan)", 2: "in two weeks"}
    rows = []
    for i in range(weeks):
        m = m0 + timedelta(weeks=i)
        rows.append({"monday": m.isoformat(), "sunday": (m + timedelta(days=6)).isoformat(),
                     "label": labels.get(i, f"in {i} weeks")})
    return rows


def context(state: dict, avg_kg: dict[str, float] | None = None) -> dict:
    """What the model needs to resolve names: ids + aliases, crops and lines, the week table."""
    today = date.fromisoformat(state["today"])
    return {
        "today": today.isoformat(),
        "weekday": today.strftime("%A"),
        "partners": [{"id": p["id"], "alias": p["alias"], "crops": sorted({k.split("/")[0] for k in p["corridor"]})}
                     for p in state["partners"]],
        "farmers": [{"id": f["id"], "alias": f["alias"], "beds": f["beds"]} for f in state["farmers"]],
        "crops": [{"id": c["id"], "name": c["name"], "lines": [l["id"] for l in c["demand_lines"]]}
                  for c in state["crops"]],
        "households": len(state.get("households", [])),
        "avg_kg_per_week": avg_kg or {},
        "weeks": week_table(today),
    }


# --- sanitize: model reading → storable proposal ---

def _week(s: str | None, today: date, default: date | None = None) -> date | None:
    if not s:
        return default
    try:
        d = monday(date.fromisoformat(s))
    except ValueError:
        return default
    lo, hi = monday(today) - timedelta(weeks=1), monday(today) + timedelta(weeks=HORIZON_WEEKS * 2)
    return d if lo <= d <= hi else default


def sanitize(r: NoteReading, state: dict) -> tuple[dict, list[str]]:
    """Clamp a reading to known ids, Monday dates and sane ranges. Returns (proposal, dropped reasons)."""
    today = date.fromisoformat(state["today"])
    partners = {p["id"] for p in state["partners"]}
    farmers = {f["id"]: set(f["crops"]) for f in state["farmers"]}
    crops = {c["id"] for c in state["crops"]}
    scopes = {"all", "channel:B2B", "channel:B2C"} | {f"partner:{p}" for p in partners}
    dropped: list[str] = []
    out: dict = {"kind": r.kind, "summary_en": r.summary_en[:300], "signals": [], "harvest_issue": None}

    if r.kind == "signals":
        for s in r.signals:
            if s.scope not in scopes:
                dropped.append(f"unknown scope {s.scope!r}")
                continue
            if s.crop is not None and s.crop not in crops:
                dropped.append(f"unknown crop {s.crop!r}")
                continue
            wf = _week(s.week_from, today)
            if wf is None:
                dropped.append(f"bad week_from {s.week_from!r}")
                continue
            wt = _week(s.week_to, today)
            if wt is not None and wt < wf:
                wt = wf
            out["signals"].append({
                "scope": s.scope, "crop": s.crop, "effect_pct": max(-100.0, min(300.0, round(s.effect_pct, 1))),
                "week_from": wf.isoformat(), "week_to": wt.isoformat() if wt else None,
                "cause": s.cause[:120], "cause_category": s.cause_category,
            })
        if not out["signals"]:
            out["kind"] = "none"
    elif r.kind == "harvest_issue" and r.harvest_issue:
        h = r.harvest_issue
        if h.farmer_id not in farmers or h.crop not in farmers[h.farmer_id]:
            dropped.append(f"unknown farmer/crop {h.farmer_id!r}/{h.crop!r}")
            out["kind"] = "none"
        else:
            hw = _week(h.harvest_week, today)
            out["harvest_issue"] = {
                "farmer_id": h.farmer_id, "crop": h.crop, "loss_pct": max(0.0, min(100.0, round(h.loss_pct, 1))),
                "delay_days": max(0, min(60, h.delay_days)), "harvest_week": hw.isoformat() if hw else None,
                "cause": h.cause[:120], "cause_category": h.cause_category,
            }
    else:
        out["kind"] = "none"
    return out, dropped


def open_end(week_from: str, week_to: str | None) -> str:
    """Signals stored for the forecast need an end week; open-ended ones run to the horizon."""
    return week_to or (date.fromisoformat(week_from) + timedelta(weeks=HORIZON_WEEKS)).isoformat()


# --- scoring (eval) ---

def bucket(pct: float) -> str:
    """Magnitude buckets the benchmark scores on: the sign plus a coarse size."""
    if pct <= -100:
        return "stop"
    a = abs(pct)
    size = "zero" if a < 1 else "small" if a < 15 else "medium" if a <= 40 else "large"
    return size if size == "zero" else f"{'+' if pct > 0 else '-'}{size}"


def _sig_fields(e: dict, g: dict | None) -> dict[str, bool]:
    g = g or {}
    return {
        "scope": e["scope"] == g.get("scope"),
        "crop": e["crop"] == g.get("crop", "∅"),
        "direction": (e["effect_pct"] > 0) == (g.get("effect_pct", 0) > 0) and "effect_pct" in g,
        "magnitude": "effect_pct" in g and bucket(e["effect_pct"]) == bucket(g["effect_pct"]),
        "period": e["week_from"] == g.get("week_from") and e["week_to"] == g.get("week_to", "∅"),
        "cause": e["cause_category"] == g.get("cause_category"),
    }


def _harvest_fields(e: dict, g: dict | None) -> dict[str, bool]:
    g = g or {}
    return {
        "farmer": e["farmer_id"] == g.get("farmer_id"),
        "crop": e["crop"] == g.get("crop"),
        "magnitude": "loss_pct" in g and abs(e["loss_pct"] - g["loss_pct"]) <= 10,
        "delay": e.get("delay_days", 0) == g.get("delay_days", 0),
        "period": e.get("harvest_week") == g.get("harvest_week"),
        "cause": e["cause_category"] == g.get("cause_category"),
    }


def expand_crops(sigs: list[dict], crops_for_scope: dict[str, list[str]]) -> list[dict]:
    """crop=null → one signal per crop the scope buys, so "pakcoy and sawi" split per crop scores the same."""
    out = []
    for s in sigs:
        if s.get("crop") is None and s.get("scope") in crops_for_scope:
            out += [{**s, "crop": c} for c in crops_for_scope[s["scope"]]]
        else:
            out.append(s)
    return out


def scope_crops(state: dict) -> dict[str, list[str]]:
    all_crops = [c["id"] for c in state["crops"]]
    m = {s: all_crops for s in ("all", "channel:B2B", "channel:B2C")}
    m.update({f"partner:{p['id']}": sorted({k.split("/")[0] for k in p["corridor"]}) for p in state["partners"]})
    return m


def score(expected: dict, got: dict, crops_for_scope: dict[str, list[str]] | None = None) -> dict:
    """Field-level comparison of one labeled note against one (sanitized) reading.

    Returns {"kind_ok", "fields": {name: bool}, "extra"} — `extra` counts predicted signals with
    no labeled counterpart (a false alarm the operator would have to reject).
    """
    res = {"kind_ok": expected["kind"] == got["kind"], "fields": {}, "extra": 0}
    if expected["kind"] == "signals":
        exp = expected["signals"]
        pool = list(got.get("signals") or [])
        if crops_for_scope:
            exp, pool = expand_crops(exp, crops_for_scope), expand_crops(pool, crops_for_scope)
        for i, e in enumerate(exp):
            # pair with the predicted signal that agrees on the most fields
            best = max(pool, key=lambda g: sum(_sig_fields(e, g).values()), default=None)
            if best is not None:
                pool.remove(best)
            for k, v in _sig_fields(e, best).items():
                res["fields"][f"s{i}.{k}"] = v
        res["extra"] = len(pool)
    elif expected["kind"] == "harvest_issue":
        for k, v in _harvest_fields(expected["harvest_issue"], got.get("harvest_issue")).items():
            res["fields"][k] = v
    else:
        res["extra"] = len(got.get("signals") or []) + (1 if got.get("harvest_issue") else 0)
    return res
