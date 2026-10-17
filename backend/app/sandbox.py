"""The sandbox: a blank farm the founder sets up and then feeds by hand, one day at a time.

Same engine, different reference: the setup doc (crop, lines, buyers with usual demand, beds
already in the ground) stands in for the demo's seed data, and the log lives in sandbox_* collections.
Closing a day uses what was entered (orders, harvests) instead of a simulated world.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app import engine
from app.allocator import BuyerOrder, HouseholdOrder, allocate_day
from app.production import bed_day, in_bed_plants, plants0, take_oldest
from app.state import apply, current_crop
from app.store import SANDBOX, Store

MAX_DAYS, MAX_BUYERS, MAX_BEDS = 400, 50, 50
WIB = timezone(timedelta(hours=7))
SETUP_ID = "current"


def today_wib() -> date:
    return datetime.now(WIB).date()


class LineIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{1,20}$")
    min_g: float = Field(gt=0)
    max_g: float = Field(gt=0)
    stretch_g: float | None = Field(default=None, gt=0)   # still accepted when short; None = max_g

    @model_validator(mode="after")
    def _order(self):
        if self.min_g >= self.max_g:
            raise ValueError(f"line {self.id}: min_g must be below max_g")
        if self.stretch_g is not None and self.stretch_g < self.max_g:
            raise ValueError(f"line {self.id}: stretch_g must be at least max_g")
        return self


class CropIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    nursery_days: int = Field(ge=0, le=60)
    growth_curve: list[tuple[float, float]] = Field(min_length=2, max_length=30)
    spread_ratio: float = Field(gt=0, le=2)
    germination: float = Field(gt=0, le=1)
    survival: float = Field(gt=0, le=1)
    seeds_per_gram: float = Field(gt=0)
    grams_per_teaspoon: float = Field(gt=0)
    max_bed_day: int = Field(ge=1, le=200)
    max_seedlings_per_sowing: int = Field(ge=1, le=100000)
    sow_weekdays: list[int] = Field(min_length=1, max_length=7)
    lines: list[LineIn] = Field(min_length=1, max_length=5)

    @field_validator("growth_curve")
    @classmethod
    def _increasing(cls, v):
        if any(b[0] <= a[0] or b[1] <= a[1] for a, b in zip(v, v[1:])):
            raise ValueError("growth curve: days and grams must both increase")
        if v[0][1] <= 0:
            raise ValueError("growth curve: grams must be above 0")
        return v

    @field_validator("sow_weekdays")
    @classmethod
    def _weekdays(cls, v):
        if any(not 0 <= d <= 6 for d in v):
            raise ValueError("sow weekdays are 0 (Mon) … 6 (Sun)")
        return sorted(set(v))


class BuyerIn(BaseModel):
    id: str | None = Field(None, pattern=r"^[a-z0-9_]{1,20}$")
    name: str = Field(min_length=1, max_length=40)
    type: Literal["business", "household"]
    line: str
    usual_kg_per_week: float = Field(0, ge=0, le=5000)
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    week_pct: list[float] = Field(default_factory=list)   # Mon..Sun % of the week's kg; empty = even over weekdays
    min_kg: float = Field(0, ge=0, le=500)

    @model_validator(mode="after")
    def _week_pct(self):
        if self.week_pct:
            if len(self.week_pct) != 7 or any(v < 0 for v in self.week_pct) or abs(sum(self.week_pct) - 100) > 0.5:
                raise ValueError(f"buyer {self.name}: weekday % must be 7 numbers (Mon…Sun) adding up to 100")
            self.weekdays = [d for d, v in enumerate(self.week_pct) if v > 0]
        return self


BED_ID = r"^[a-z0-9_]{1,20}-\d{4}-\d{2}-\d{2}-\d{1,3}$"     # <line>-<sown on>-<number>; the number names "Bed N"


class BedIn(BaseModel):
    id: str | None = Field(None, pattern=BED_ID)
    line: str
    sown_on: date
    seedlings: int = Field(gt=0, le=100000)


class SetupIn(BaseModel):
    start: date = Field(default_factory=today_wib)
    learn_reference: bool = True
    crop: CropIn
    buyers: list[BuyerIn] = Field(default_factory=list, max_length=MAX_BUYERS)
    beds: list[BedIn] = Field(default_factory=list, max_length=MAX_BEDS)
    month_pct: list[float] = Field(default_factory=lambda: [25.0] * 4)      # dates 1–7, 8–14, 15–21, 22–end
    year_index: list[float] = Field(default_factory=lambda: [100.0] * 12)   # Jan..Dec, 100 = a normal month

    @field_validator("month_pct")
    @classmethod
    def _month(cls, v):
        if len(v) != 4 or any(x < 0 for x in v) or abs(sum(v) - 100) > 0.5:
            raise ValueError("month % must be 4 numbers (dates 1–7, 8–14, 15–21, 22–end) adding up to 100")
        return v

    @field_validator("year_index")
    @classmethod
    def _year(cls, v):
        if len(v) != 12 or any(not 0 <= x <= 500 for x in v):
            raise ValueError("year index must be 12 numbers (Jan…Dec) between 0 and 500, 100 = normal")
        return v

    @model_validator(mode="after")
    def _consistent(self):
        lines = {ln.id for ln in self.crop.lines}
        names, ids = set(), set()
        for i, b in enumerate(self.buyers, 1):
            if b.line not in lines:
                raise ValueError(f"buyer {b.name}: unknown line {b.line!r}")
            if b.name in names:
                raise ValueError(f"buyer name {b.name!r} is used twice")
            names.add(b.name)
            if b.id is None:
                b.id = next(f"b{n}" for n in range(i, i + MAX_BUYERS + 1) if f"b{n}" not in ids
                            and all(o.id != f"b{n}" for o in self.buyers))
            if b.id in ids:
                raise ValueError(f"buyer id {b.id!r} is used twice")
            ids.add(b.id)
            if any(not 0 <= d <= 6 for d in b.weekdays):
                raise ValueError(f"buyer {b.name}: weekdays are 0 (Mon) … 6 (Sun)")
        nos = [bed_no(b.id) for b in self.beds if b.id]
        if len(nos) != len(set(nos)):
            raise ValueError("two beds share one number")
        for b in self.beds:
            if b.line not in lines:
                raise ValueError(f"bed: unknown line {b.line!r}")
            if b.sown_on > self.start:
                raise ValueError(f"bed sown {b.sown_on} is after the start {self.start}")
        return self


def default_setup() -> dict:
    """A blank farm with the pakcoy curve and both lines filled in (the founder edits from there)."""
    return {"start": today_wib().isoformat(), "learn_reference": True,
            "crop": {"name": "Pakcoy", "nursery_days": 15,
                     "growth_curve": [[0, 5], [7, 15], [14, 45], [18, 70], [21, 100], [24, 125], [27, 145], [30, 160]],
                     "spread_ratio": 0.45, "germination": 0.85, "survival": 0.9, "seeds_per_gram": 400,
                     "grams_per_teaspoon": 3, "max_bed_day": 30, "max_seedlings_per_sowing": 3000, "sow_weekdays": [0, 3],
                     "lines": [{"id": "regular", "min_g": 100, "max_g": 140, "stretch_g": 160},
                               {"id": "baby", "min_g": 50, "max_g": 70, "stretch_g": 80}]},
            "buyers": [], "beds": []}


def example_setup(today: date) -> dict:
    """The founder's own baby-pakcoy farm (saved in the sandbox 2026-10-17), around `today`: one line, a
    restaurant with a weekend-leaning week plus weekend retail pre-orders, payday month, Dec–Jan up and Jul–Aug
    down. Bed ages are kept, not dates (the 9-day bed keeps early November covered). For the demo and the video: Load example farm → Save →
    a full Today card from day one."""
    s = default_setup()
    crop = {**s["crop"],
            "growth_curve": [[0, 1], [7, 15], [14, 50], [18, 70], [21, 100], [24, 160], [28, 200], [35, 250]],
            "lines": [{"id": "baby", "min_g": 50, "max_g": 70, "stretch_g": 100}]}
    return {**s, "crop": crop, "start": today.isoformat(),
            "month_pct": [30, 26, 24, 20], "year_index": [120, 100, 100, 100, 100, 100, 80, 70, 100, 100, 100, 120],
            "buyers": [{"name": "Resto WKS", "type": "business", "line": "baby", "usual_kg_per_week": 35,
                        "week_pct": [14.3, 12.3, 11.3, 10.3, 16.3, 18.3, 17.2], "min_kg": 0},
                       {"name": "Retails", "type": "business", "line": "baby", "usual_kg_per_week": 5,  # weekend pre-orders
                        "week_pct": [0, 0, 0, 0, 0, 40, 60], "min_kg": 0}],
            "beds": [{"line": "baby", "sown_on": (today - timedelta(days=age)).isoformat(), "seedlings": n}
                     for age, n in ((30, 1000), (23, 1000), (16, 1000), (9, 1000), (2, 1000))]}


def bed_no(bed_id: str) -> int:
    return int(bed_id.rsplit("-", 1)[1])


def _event_buyers(events: list[dict]) -> set[str]:
    out: set[str] = set()
    for doc in events:
        for ev in doc.get("events", []):
            out |= {ev[k] for k in ("buyer", "household") if isinstance(ev.get(k), str)}
            if str(ev.get("scope", "")).startswith("buyer:"):
                out.add(ev["scope"][6:])
            if str(ev.get("series", "")).startswith("b2b:"):
                out.add(ev["series"].split(":")[1])
    return out


def keep_ids(body: dict, old: dict | None, events: list[dict]) -> dict:
    """Give the id-less buyers and beds of a setup body stable ids before validation, so a re-pasted sheet
    or an added row never shifts history onto someone else: a buyer keeps the id of the old buyer with
    its name, a bed the id of an old bed with its line, date and seedlings; anything new gets a number
    never used before (by the old setup, the body, or the log)."""
    if not isinstance(body, dict):
        return body
    body = json.loads(json.dumps(body))
    buyers = [b for b in body.get("buyers") or [] if isinstance(b, dict)] if isinstance(body.get("buyers"), list) else []
    beds = [b for b in body.get("beds") or [] if isinstance(b, dict)] if isinstance(body.get("beds"), list) else []
    old_buyers = (old or {}).get("buyers", [])
    by_name = {b["name"]: b["id"] for b in old_buyers}
    used = {b["id"] for b in old_buyers} | {b["id"] for b in buyers if b.get("id")} | _event_buyers(events)
    n = max((int(i[1:]) for i in used if re.fullmatch(r"b\d+", str(i))), default=0)
    taken = {b["id"] for b in buyers if b.get("id")}
    for b in buyers:
        if not b.get("id"):
            b["id"] = by_name.get(b.get("name"))
            if b["id"] is None or b["id"] in taken:
                n += 1
                b["id"] = f"b{n}"
            taken.add(b["id"])
    old_beds = reference(old)["batches"] if old else []
    kept = {b["id"] for b in beds if b.get("id")}
    free = [b for b in old_beds if b["id"] not in kept]
    n = max([bed_no(b["id"]) for b in old_beds] + [bed_no(i) for i in kept if re.fullmatch(BED_ID, str(i))], default=0)
    fresh = []
    for b in beds:
        if b.get("id"):
            continue
        twin = next((o for o in free if (o["line"], o["sown_on"], o["seedlings"]) == (b.get("line"), b.get("sown_on"),
                                                                                     b.get("seedlings"))), None)
        if twin:
            free.remove(twin)
            b["id"] = twin["id"]
        else:
            fresh.append(b)
    for b in sorted(fresh, key=lambda b: str(b.get("sown_on"))):      # new beds: numbered by sowing date
        n += 1
        b["id"] = f"{b.get('line')}-{b.get('sown_on')}-{n}"
    return body


def _week(b: dict) -> list[float]:
    if b.get("week_pct"):
        return [round(b["usual_kg_per_week"] * p / 100, 4) for p in b["week_pct"]]
    days = b["weekdays"] or list(range(7))
    per = b["usual_kg_per_week"] / len(days)
    return [round(per, 4) if d in days else 0.0 for d in range(7)]


def priors_from_setup(s: dict) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for b in s["buyers"]:
        key = engine.b2b_key(b["id"], b["line"]) if b["type"] == "business" else engine.hh_key(b["line"])
        out[key] = [round(a + w, 4) for a, w in zip(out.get(key, [0.0] * 7), _week(b))]
    for ln in s["crop"]["lines"]:                 # a line with households but no estimate still gets a series
        if any(b["type"] == "household" and b["line"] == ln["id"] for b in s["buyers"]):
            out.setdefault(engine.hh_key(ln["id"]), [0.0] * 7)
    return out


def _key(s: dict) -> str:
    return hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest()[:16]


@lru_cache(maxsize=64)
def _reference(raw: str) -> dict:
    s = json.loads(raw)
    start = date.fromisoformat(s["start"])
    crop = {"id": "crop", **{k: v for k, v in s["crop"].items()},
            "lines": [{**ln, "channels": ["B2B", "B2C"]} for ln in s["crop"]["lines"]]}
    biz = [b for b in s["buyers"] if b["type"] == "business"]
    hh = [b for b in s["buyers"] if b["type"] == "household"]
    beds = sorted(s["beds"], key=lambda b: b["sown_on"])
    # a saved bed keeps its id (and so its number); a setup without ids numbers its beds by sowing date
    ids = [b.get("id") or f"{b['line']}-{b['sown_on']}-{i}" for i, b in enumerate(beds, 1)]
    batches = [{"id": i, "label": f"Bed {bed_no(i)}", "line": b["line"], "sown_on": b["sown_on"],
                "seedlings": b["seedlings"]} for i, b in zip(ids, beds)]
    last = {ln["id"]: max((b["sown_on"] for b in beds if b["line"] == ln["id"]), default=None) for ln in s["crop"]["lines"]}
    return {
        "crops": [crop],
        "buyers": [{"id": b["id"], "alias": b["name"], "weekdays": b["weekdays"],
                    "lines": {b["line"]: {"kg": round(sum(_week(b)) / max(1, sum(1 for v in _week(b) if v)), 2),
                                          "min_kg": b["min_kg"]}}} for b in biz],
        "households": [{"id": b["id"], "alias": b["name"], "line": b["line"],
                        "kg": round(b["usual_kg_per_week"] / 7, 2), "weekdays": b["weekdays"]} for b in hh],
        "batches": batches,
        "history": [],
        "meta": {"day0": start.isoformat(), "shape_until": start.isoformat(), "sandbox": True, "synthetic": False,
                 "learn_reference": s["learn_reference"], "priors": priors_from_setup(s),
                 "season": {"month_pct": s.get("month_pct", [25] * 4), "year_index": s.get("year_index", [100] * 12)},
                 "household_ids": [b["id"] for b in hh], "rev": _key(s),
                 "last_sown": {k: v for k, v in last.items() if v}, "next_bed": max(map(bed_no, ids), default=0) + 1},
    }


def reference(setup: dict) -> dict:
    return _reference(json.dumps(setup, sort_keys=True))


DERIVED = ("crops", "buyers", "households", "batches", "history")


class SandboxStore:
    """The visitor's store, seen through the sandbox: reference from the setup, log in sandbox_*."""

    def __init__(self, base: Store, setup: dict | None):
        self.base, self.setup = base, setup or SetupIn.model_validate(default_setup()).model_dump(mode="json")
        self.saved = setup is not None
        self.uid = f"{base.uid}#sandbox"

    def list(self, collection: str) -> list[dict]:
        if collection in DERIVED:
            return reference(self.setup)[collection]
        return self.base.list(f"sandbox_{collection}")

    def get(self, collection: str, id: str) -> dict | None:
        return self.base.get(f"sandbox_{collection}", id)

    def put(self, collection: str, doc: dict) -> dict:
        return self.base.put(f"sandbox_{collection}", doc)

    def add(self, collection: str, doc: dict) -> bool:
        return self.base.add(f"sandbox_{collection}", doc)

    def delete(self, collection: str, id: str) -> None:
        self.base.delete(f"sandbox_{collection}", id)

    def meta(self) -> dict:
        return reference(self.setup)["meta"]

    def reset(self, collections: tuple[str, ...] = SANDBOX) -> None:
        self.base.reset(collections)

    def for_user(self, uid: str) -> SandboxStore:
        return SandboxStore(self.base.for_user(uid), self.setup)


def open_sandbox(base: Store) -> SandboxStore:
    doc = base.get("sandbox_setup", SETUP_ID)
    if doc is None:
        return SandboxStore(base, None)
    return SandboxStore(base, json.loads(doc["json"]) if "json" in doc else doc["setup"])


def setup_doc(setup: dict) -> dict:
    """The stored form: one JSON string, since Firestore cannot hold the curve's arrays inside an array."""
    return {"id": SETUP_ID, "json": json.dumps(setup, sort_keys=True)}


def close_day(st, crop, buyers: list[dict], households: list[dict], plans) -> list[dict]:
    """Today (t) → tomorrow (t+1) from what was entered: tomorrow's orders are served from the harvest
    logged for it (or, if none, the engine's planned send, harvested oldest-first). A buyer's actual is
    their order (0 kg included); no order logged is unknown, not 0, so the level doesn't learn from it.
    A one-off order is served but never learned from: no actual for that buyer, left out of the households sum."""
    t = st.today
    d = t + timedelta(days=1)
    iso = d.isoformat()
    by_id = {b["id"]: b for b in buyers}
    hh_ids = {h["id"] for h in households}
    evs: list[dict] = []
    for ln in crop.lines:
        line = ln.id
        orders = {(who, kg) for (day, who, l2), kg in st.known_orders.items() if day == iso and l2 == line}
        b2b = [BuyerOrder(w, kg, by_id[w]["lines"][line]["min_kg"]) for w, kg in sorted(orders)
               if w in by_id and line in by_id[w]["lines"]]
        hh = [HouseholdOrder(w, kg, st.last_shorted.get(w)) for w, kg in sorted(orders) if w in hh_ids]
        logged = st.harvested.get((t.isoformat(), line), 0.0) + st.harvested.get((iso, line), 0.0)
        got = logged
        if not logged and plans[line].send > 0:
            shadows = [replace(b) for b in st.alive(crop, line)]
            for b, kg in take_oldest(crop, shadows, d, plans[line].send):
                evs.append({"t": "harvest", "batch": b.id, "day": iso, "kg": round(kg, 2), "assumed": True})
                got += round(kg, 2)
        rows_b, rows_h = allocate_day(got, b2b, hh, d)
        evs += [{"t": "short", "household": r.customer_id, "day": iso} for r in rows_h if r.short_kg > 0]
        evs.append({"t": "served", "day": iso, "line": line,
                    "b2b_ordered": round(sum(r.ordered_kg for r in rows_b), 2),
                    "b2b_served": round(sum(r.served_kg for r in rows_b), 2),
                    "hh_ordered": round(sum(r.ordered_kg for r in rows_h), 2),
                    "hh_served": round(sum(r.served_kg for r in rows_h), 2), "waste_kg": 0.0})
        for b in buyers:
            if line not in b["lines"]:
                continue
            kg = dict(orders).get(b["id"])
            if kg is not None and (iso, b["id"], line) not in st.oneoff_orders:
                evs.append({"t": "actual", "series": engine.b2b_key(b["id"], line), "day": iso, "kg": kg})
        if any(h["line"] == line for h in households):
            evs.append({"t": "actual", "series": engine.hh_key(line), "day": iso,
                        "kg": round(sum(kg for w, kg in orders
                                        if w in hh_ids and (iso, w, line) not in st.oneoff_orders), 2)})
    evs.append({"t": "clock", "day": iso})
    return evs


def _day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%a} {d.day} {d:%b}"


def orphan_orders(st, buyers: dict[str, set[str]]) -> list[str]:
    """Orders still to come whose buyer is gone or no longer buys that line (a setup edit would strand them)."""
    t = st.today.isoformat()
    return [f"{who} · {line} · {day}" for (day, who, line), kg in sorted(st.known_orders.items())
            if day > t and kg > 0 and line not in buyers.get(who, set())]


def describe(ev: dict, names: dict[str, str], labels: dict[str, str]) -> str:
    """One fixed-format line per event, for the confirm card and the trail."""
    who = lambda i: names.get(i, f"⚠ unknown buyer {i}")
    bed = lambda i: labels.get(i, f"⚠ unknown bed {i}")
    t = ev["t"]
    if t == "order":
        amount = f"{ev['kg']:.1f} kg" if ev["kg"] else "no order"
        once = " · one-off" if ev.get("oneoff") else ""
        return f"ORDER · {who(ev['buyer'])} · {ev['line']} · {amount} · {_day(ev['day'])}{once}"
    if t == "harvest":
        s = f" · sample {ev['big5_g']:.0f} g / {ev['small5_g']:.0f} g" if ev.get("big5_g") else ""
        a = " · assumed (planned send)" if ev.get("assumed") else ""
        return f"HARVEST · {bed(ev['batch'])} · {ev['kg']:.1f} kg{s}{a}"
    if t == "sow":
        return f"SOW · {ev['line']} · {ev['seedlings']} seedlings · {_day(ev['day'])}"
    if t == "postpone":
        return f"POSTPONE · {ev['line']} · sowing of {_day(ev['day'])} · {ev.get('reason', '')}".rstrip(" ·")
    if t == "loss" and ev.get("recount"):
        seen = "empty" if not ev["left_pct"] else f"{ev['left_pct']:g}% of full seen"
        return f"LEFT · {bed(ev['batch'])} · {seen} · {ev['plants']} plants fewer than the app counted"
    if t == "loss":
        return f"LOSS · {bed(ev['batch'])} · {ev['pct']:.0f}% · {ev.get('cause', '')}".rstrip(" ·")
    if t == "signal":
        return (f"SIGNAL · {ev['scope']}{' · ' + ev['line'] if ev.get('line') else ''} · {ev['effect_pct']:+.0f}% · "
                f"{_day(ev['date_from'])}–{_day(ev['date_to'])}")
    if t == "reference_reset":
        return "RESET · reference curve back to the starting curve"
    return t.upper()


def buyer_lines(ws: Store) -> dict[str, set[str]]:
    """Every buyer (households included) → the lines they buy."""
    return ({b["id"]: set(b["lines"]) for b in ws.list("buyers")}
            | {h["id"]: {h["line"]} for h in ws.list("households")})


def form_events(raw: dict, st, crop, labels: dict[str, str], buyers: dict[str, set[str]]) -> list[dict]:
    """One form submission → primitive events dated the sandbox's today. Raises ValueError with a
    sentence for people. buyers: buyer id → the lines they buy."""
    try:
        return _form_events(raw, st, crop, buyers)
    except (KeyError, TypeError) as e:
        raise ValueError(f"missing or malformed field {e}") from e


def _seen_left(st, crop, harvest: dict, seen: float) -> list[dict]:
    """The farmer's look at a bed after cutting: `seen` % of a full bed (seedlings × survival) still stands.
    Fewer than the app counts → the rest is gone (sorted out, never there), a loss, not oversize waste. More
    → kept as counted for now; harvest_warnings says so."""
    after = copy.deepcopy(st)
    apply(after, crop, harvest)
    c, b = current_crop(after, crop), after.batches[harvest["batch"]]
    left, target = in_bed_plants(c, b, st.today), seen / 100 * plants0(c, b)
    if left - target <= 0.5:
        return []
    return [{"t": "loss", "batch": b.id, "day": st.today.isoformat(), "pct": round((left - target) / left * 100, 2),
             "cause": "seen left after harvest", "recount": True, "left_pct": round(seen, 1),
             "plants": round(left - target)}]


def _form_events(raw: dict, st, crop, buyers: dict[str, set[str]]) -> list[dict]:
    k, t = raw.get("kind"), st.today
    lines = {ln.id for ln in crop.lines}
    def line_of(x):
        if x not in lines:
            raise ValueError(f"unknown line {x!r}")
        return x
    def kg_of(x, hi=500.0, zero=False):
        x = float(x)
        if not (0 <= x if zero else 0 < x) or x > hi:
            raise ValueError(f"kg must be {'0' if zero else 'above 0'} … {hi:g}")
        return round(x, 2)
    def bed_of(x):
        if x not in st.batches:
            raise ValueError(f"unknown bed {x!r}")
        return x
    if k == "order":
        d = date.fromisoformat(raw["day"])
        if not t < d <= t + timedelta(days=14):
            raise ValueError("an order is for tomorrow or up to 14 days ahead")
        if raw.get("buyer") not in buyers:
            raise ValueError(f"unknown buyer {raw.get('buyer')!r}")
        if line_of(raw["line"]) not in buyers[raw["buyer"]]:
            raise ValueError(f"this buyer is not set up for the {raw['line']} line; change the buyer in Setup first")
        if raw.get("oneoff") and (key := (d.isoformat(), raw["buyer"], raw["line"])) in st.known_orders \
                and key not in st.oneoff_orders:
            raise ValueError("this buyer already has a regular order for that day; change it to the total, "
                             "or tick One-off for the whole amount")
        ev = {"t": "order", "day": d.isoformat(), "buyer": raw["buyer"], "line": raw["line"],
              "kg": kg_of(raw["kg"], zero=True)}                     # 0 = "no order this time", a real zero
        return [ev | {"oneoff": True}] if raw.get("oneoff") else [ev]
    if k == "harvest":
        ev = {"t": "harvest", "batch": bed_of(raw.get("batch")), "day": t.isoformat(), "kg": kg_of(raw["kg"], 5000)}
        if raw.get("big5_g") or raw.get("small5_g"):
            big, small = float(raw["big5_g"]), float(raw["small5_g"])
            if not big >= small > 0:
                raise ValueError("sample: the 5 biggest must weigh at least the 5 smallest, both above 0")
            ev |= {"big5_g": big, "small5_g": small}
        seen = 0.0 if raw.get("empty") else raw.get("left_pct")
        if seen in (None, ""):
            return [ev]
        seen = float(seen)
        if not 0 <= seen <= 100:
            raise ValueError("left in the bed must be 0 … 100% of a full bed")
        ev["seen_pct"] = round(seen, 1)                 # kept for learning yield later, even when nothing is cut
        return [ev, *_seen_left(st, crop, ev, seen)]
    if k == "sow":
        n = int(raw.get("seedlings", 0))
        if not 0 < n <= crop.max_seedlings:
            raise ValueError(f"seedlings must be 1 … {crop.max_seedlings}")
        return [{"t": "sow", "line": line_of(raw["line"]), "day": t.isoformat(), "seedlings": n}]
    if k == "postpone":
        line = line_of(raw["line"])
        sown = st.last_sown.get(line) == t or (line, t.isoformat()) in st.postponed
        day = engine.next_sow_day(t, sown, crop.sow_weekdays)
        return [{"t": "postpone", "line": line, "day": day.isoformat(), "reason": str(raw.get("reason", ""))[:80]}]
    if k == "loss":
        pct = float(raw["pct"])
        if not 0 < pct <= 100:
            raise ValueError("loss % must be above 0 and at most 100")
        cause = str(raw.get("cause", ""))[:80]
        ids = [bed_of(raw["batch"])] if raw.get("batch") else [
            b.id for b in st.alive(crop, line_of(raw["line"])) if bed_day(crop, b, t) >= 0 and in_bed_plants(crop, b, t) > 0]
        if not ids:
            raise ValueError("no bed in the ground on that line")
        return [{"t": "loss", "batch": i, "day": t.isoformat(), "pct": pct, "cause": cause} for i in ids]
    if k == "signal":
        scopes = {"all", "channel:B2B", "channel:B2C"} | {f"buyer:{b}" for b in buyers}
        if raw.get("scope") not in scopes:
            raise ValueError(f"unknown scope {raw.get('scope')!r}")
        line = line_of(raw["line"]) if raw.get("line") else None
        pct = float(raw["effect_pct"])
        if not -100 <= pct <= 300:
            raise ValueError("effect % must be between -100 and +300")
        d0 = date.fromisoformat(raw["date_from"])
        d1 = date.fromisoformat(raw["date_to"]) if raw.get("date_to") else t + timedelta(days=182)
        if not t <= d0 <= d1 <= t + timedelta(days=182):
            raise ValueError("signal dates run from today, up to 182 days ahead, and from ≤ to")
        return [{"t": "signal", "scope": raw["scope"], "line": line, "effect_pct": round(pct, 1),
                 "date_from": d0.isoformat(), "date_to": d1.isoformat(), "cause": str(raw.get("cause", ""))[:120]}]
    if k == "reference_reset":
        return [{"t": "reference_reset", "day": t.isoformat()}]
    raise ValueError(f"unknown form {k!r}")
