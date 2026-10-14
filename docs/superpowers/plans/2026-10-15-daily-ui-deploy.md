# Daily engine — Plan 2: UI, re-seed, deploy, write-up — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the daily engine (Plan 1, branch `feat/daily-engine`) in front of judges: a six-tab UI on the real API, Firestore re-seeded with the daily dataset, deployed to https://tanam-secukupnya.web.app, plus README and REPORT.

**Architecture:** The Next.js static UI is rewritten against the seven read routes and four write routes that Plan 1 shipped (shapes pinned by a new backend contract test). One loader fetches `/state /today /beds /tomorrow /sow /demand` after every change; Season loads once. Pure formatting and wording live in `frontend/lib/format.ts`, unit-tested with Vitest; tabs are thin views. Deploy is the existing `just deploy` recipe, run by hand, behind a founder gate.

**Tech Stack:** Next.js 15 (static export) + React 19 + recharts 3, Vitest 3 (new, dev only), FastAPI + pytest, Firestore, Firebase Hosting/Auth, Cloud Run, Cloud Build.

**Spec:** `docs/superpowers/specs/2026-10-14-daily-engine-design.md` (§10 API and UI, §8 data, §9 season, §12 schedule). Plan 1: `docs/superpowers/plans/2026-10-14-daily-engine.md`.

## Global Constraints

- Everything a judge sees is **English**; aliases only (“Restaurant A”, “Household 03”) — no real names (D10).
- Data is synthetic and must say so: show the `synthetic data` pill when `state.synthetic` is true.
- Units: kg with at most 2 decimals; seedlings with thousands separators (`1,350`); seeds as `≈ 4.0 g ≈ 1⅓ tsp`.
- Tabs, in order: **Today, Beds, Tomorrow, Sow, Demand, Season** (spec §10).
- A person Accepts or Rejects every note before anything changes (D8) — the UI never auto-accepts.
- Phone first: usable at 360 px wide, no horizontal page scroll (tables scroll inside their card).
- No deploy and no merge to `main` without the founder saying so (Task 9 is gated).
- Run the real `npm run build` before any deploy (`tsc --noEmit` alone missed a prod crash once).
- Local dev ports: API `:8100` (`just api`), UI `:3100`. Port 8000 belongs to another project.
- `just` is not on the WSL PATH: run recipe lines by hand where a step says so.
- Commit trailer on every commit:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01MftAmfkzBGrgr3FPofiv8F
  ```

## Review Focus

1. **The day moved under an open screen** (two tabs open, or a double-click on “Next day”): `POST /day/next` with a stale `from_day` appends nothing and returns `appended: 0`; the UI must just reload, not show an error. Accepting a note read on an earlier day returns 409 “read it again”; the card must show that text and offer **Read again** and **Reject** (also closes deferred minor #5). → `friendly()` tests in Task 1; Read-again button in Task 2.
2. **Gemini refuses** (429 daily cap, 502 model error, network down): the note box shows one plain sentence, keeps the typed text, and stays usable. → `friendly()` tests in Task 1.
3. **Old weekly-app data in a returning visitor's workspace** (`users/{uid}/notes` holds notes with the old proposal shape; `signals`, `runs` subcollections): `today.pending` would hand the UI a note it cannot render. → Task 9 wipes old workspaces during the re-seed; Task 2's `NoteCard` renders an unknown/partial proposal as its summary only (`proposalLines` test with a legacy note).
4. **A line with nothing in it** (baby has no B2B buyers; a Saturday with zero need; a line with no batches in the bed): tables show a one-line empty state instead of an empty table or `NaN`. → `kg()`/`daySentence()` zero tests in Task 1; empty states in Tasks 3–4.
5. **The demo never runs short**: walking the clock with no notes shows 0 kg short for 28 days (checked 2026-10-15), so the video's key moment — ceiling below need, households rotating, borrowing — only appears after a loss or postponed-sowing note. → Task 8 pins that a loss note produces a visible shortfall story within a few days; if it does not, stop and bring it to the founder (do not tune the engine silently).

---

## File map

| File | Responsibility | Task |
|---|---|---|
| `backend/tests/test_api_contract.py` | pins the JSON keys the UI reads, per route | 1 |
| `frontend/lib/types.ts` | TypeScript shapes of every API response (replaces the weekly types) | 1 |
| `frontend/lib/api.ts` | `call()` + `ApiError`, one function per route | 1 |
| `frontend/lib/firebase.ts` | add `NEXT_PUBLIC_AUTH=off` bypass for local dev/screenshots | 1 |
| `frontend/lib/format.ts` (+ `format.test.ts`) | pure wording: kg, dates, tsp, day sentence, proposal lines, friendly errors | 1 |
| `frontend/app/page.tsx` | shell: header clock bar (Next day / +7 / Reset), tab nav, loader | 1 |
| `frontend/components/TodayTab.tsx`, `NoteCard.tsx` | Today: summary, note box, pending notes | 2 |
| `frontend/components/BedsTab.tsx` | Beds: chart + batch table per line | 3 |
| `frontend/components/TomorrowTab.tsx` | Tomorrow: ceiling, who is served/rotated, borrowing | 4 |
| `frontend/components/SowTab.tsx` | Sow: next sowing per line + breakdown | 5 |
| `frontend/components/SeasonTab.tsx` | Season: 3 strategies, 5 seeds, sowing swing chart | 6 |
| `frontend/components/DemandTab.tsx` | Demand: band chart, levels, market factor, signals | 7 |
| `backend/tests/test_demo_story.py` | the video's shortfall moment exists | 8 |
| `scripts/seed_firestore.py` | drop obsolete collections + old workspaces | 9 |
| `README.md`, `REPORT.md` | judge-facing write-up | 10 |
| `backend/app/{gemini,farm,main}.py`, `TodayTab.tsx` | G5 “Why?” (optional, cut first) | 11 |

Deleted in Task 1: `frontend/components/{CommitmentsTab,ForecastTab,InputsTab,LinePicker,PlanTab,ScenarioTab}.tsx`, `frontend/lib/series.ts`.

Screenshot helper used by every UI task (Windows Edge headless, from WSL; the UI dev server must run with auth off):

```bash
# terminal 1: just api        (or: cd backend && AUTH=off uv run uvicorn app.main:app --reload --port 8100)
# terminal 2: cd frontend && NEXT_PUBLIC_AUTH=off npx next dev -p 3100
shot() {  # shot <tab> <width>
  mkdir -p .shots
  "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu \
    --window-size="$2",1600 --virtual-time-budget=10000 \
    --screenshot="$(wslpath -w "$PWD/.shots/$1-$2.png")" "http://localhost:3100/#$1"
}
```

`.shots/` is git-ignored. Look at each PNG with the Read tool.

---

### Task 1: API contract, types, format helpers, shell

**Files:**
- Create: `backend/tests/test_api_contract.py`, `frontend/lib/format.ts`, `frontend/lib/format.test.ts`, `frontend/vitest.config.ts`
- Rewrite: `frontend/lib/types.ts`, `frontend/lib/api.ts`, `frontend/app/page.tsx`
- Modify: `frontend/lib/firebase.ts`, `frontend/package.json`, `frontend/app/globals.css`, `frontend/app/layout.tsx`
- Delete: the six weekly components and `frontend/lib/series.ts`

**Interfaces:**
- Consumes: the API as it stands on `feat/daily-engine` (22905ea).
- Produces (used by Tasks 2–7, 11):
  - `types.ts`: `State, Today, TodayLine, NoteDoc, Proposal, Signal, Beds, BedsLine, BatchRow, Tomorrow, TomorrowLine, Sow, SowLine, Demand, Season, Data`
  - `api.ts`: `api.{state,today,beds,tomorrow,sow,demand,season,readNote,decideNote,nextDay,reset}`, `class ApiError { status: number; detail: string }`
  - `format.ts`: `kg(n)`, `shortDate(iso)`, `tsp(x)`, `int(n)`, `lineName(id)`, `daySentence(line)`, `scopeName(scope, state)`, `proposalLines(p, state)`, `friendly(err)`
  - `page.tsx`: tab registry `TABS: { id, label, hint, view: (p: TabProps) => JSX }[]` with `TabProps = { data: Data; reload: () => Promise<void> }`

- [ ] **Step 1: Write the backend contract test**

`backend/tests/test_api_contract.py`:

```python
"""The UI (frontend/lib/types.ts) reads exactly these keys. If a route changes shape, this fails first."""

import pytest
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def fresh():
    client.post("/api/demo/reset")
    yield
    client.post("/api/demo/reset")


def keys(d: dict) -> set[str]:
    return set(d)


def test_state_shape():
    s = client.get("/api/state").json()
    assert keys(s) >= {"today", "synthetic", "crop", "buyers", "households", "senders"}
    assert keys(s["crop"]) >= {"name", "lines", "nursery_days", "germination", "survival"}
    assert keys(s["buyers"][0]) >= {"id", "alias", "segment", "lines"}
    assert keys(s["senders"][0]) == {"id", "alias"}


def test_today_shape():
    t = client.get("/api/today").json()
    assert keys(t) == {"today", "weekday", "lines", "pending"}
    ln = t["lines"][0]
    assert keys(ln) == {"line", "need_kg", "ceiling_kg", "send_kg", "short_kg", "rotated", "sow"}
    assert keys(ln["sow"]) == {"day", "weekday", "seedlings", "seeds_g", "teaspoons", "shortfall_ahead_kg"}


def test_beds_shape():
    b = client.get("/api/beds").json()["lines"][0]
    assert keys(b) == {"line", "min_g", "max_g", "batches", "chart"}
    assert keys(b["batches"][0]) == {"id", "label", "sown_on", "bed_day", "stage", "seedlings", "plants_left", "avg_g",
                                     "offset_days", "spread", "sampled", "ready_from", "until",
                                     "available_tomorrow_kg", "waste_plants"}
    assert keys(b["chart"][0]) == {"day", "available_kg", "need_kg", "short_kg"}
    assert len(b["chart"]) == 40


def test_tomorrow_shape():
    ln = client.get("/api/tomorrow").json()["lines"][0]
    assert keys(ln) == {"line", "day", "need_kg", "available_kg", "ceiling_kg", "send_kg", "short_kg", "buyers",
                        "households", "borrowing"}
    assert keys(ln["buyers"][0]) == {"id", "alias", "known", "ordered_kg", "served_kg", "min_kg"}
    assert keys(ln["households"][0]) == {"id", "alias", "ordered_kg", "served_kg"}


def test_sow_shape():
    ln = client.get("/api/sow").json()["lines"][0]
    assert keys(ln) == {"line", "day", "seedlings", "seeds_g", "teaspoons", "ready_from", "covers_until", "gap_kg",
                        "capped", "shortfall_ahead", "missed", "postponed", "basis"}


def test_demand_shape():
    d = client.get("/api/demand").json()
    assert keys(d) == {"today", "market", "series", "signals", "lines"}
    assert keys(d["market"]) == {"factor", "buyers", "text"}
    assert keys(d["series"][0]) == {"key", "label", "line", "usual_kg", "level_kg", "shape"}
    assert keys(d["lines"][0]["days"][0]) == {"day", "low", "expected", "high", "protected", "target"}


def test_season_shape():
    s = client.get("/api/season").json()
    assert keys(s) >= {"days", "seeds", "main_seed", "summary", "runs", "sowings", "synthetic"}
    assert set(s["summary"]) == {"cobweb", "fixed", "tanam"}
    assert keys(s["summary"]["tanam"]) == {"waste_pct", "b2b_fill_pct", "hh_fill_pct", "sowing_cv"}
    assert keys(s["runs"][0]) == {"strategy", "seed", "waste_pct", "b2b_fill_pct", "hh_fill_pct", "sowing_cv"}
    assert keys(s["sowings"]["tanam"][0]) == {"line", "day", "seedlings"}


def test_next_day_shape():
    r = client.post("/api/day/next", json={"from_day": "2026-10-12"}).json()
    assert r == {"today": "2026-10-13", "appended": 1}
    assert client.post("/api/day/next", json={"from_day": "2026-10-12"}).json() == {"today": "2026-10-13", "appended": 0}
```

- [ ] **Step 2: Run it — it should pass already (it documents Plan 1's API)**

Run: `uv run --project backend pytest -q backend/tests/test_api_contract.py`
Expected: `8 passed`. If any fails, the API differs from the 2026-10-15 dump this plan was written against: fix the **test and the matching type in Step 6** to the real shape (the API is the source of truth), and note it in the ledger.

- [ ] **Step 3: Add Vitest**

```bash
cd frontend && npm install -D vitest@3.2.4
```

`frontend/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: { include: ["lib/**/*.test.ts"] },
});
```

In `frontend/package.json` scripts add `"test": "vitest run"`.

- [ ] **Step 4: Write the failing format tests**

`frontend/lib/format.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { daySentence, friendly, int, kg, lineName, proposalLines, scopeName, shortDate, tsp } from "./format";
import type { Proposal, State, TodayLine } from "./types";

const state = {
  today: "2026-10-12",
  synthetic: true,
  buyers: [{ id: "resto_a", alias: "Restaurant A", segment: "restaurant", weekdays: [], lines: {} }],
  households: [],
  senders: [],
} as unknown as State;

const empty: Proposal = { kind: "none", summary_en: "", orders: [], harvest: null, sowing: null, loss: null, signals: [] };

describe("numbers and dates", () => {
  it("kg keeps 1 decimal from 10 kg up, 2 below, and plain 0", () => {
    expect(kg(37.17)).toBe("37.2 kg");
    expect(kg(1.76)).toBe("1.76 kg");
    expect(kg(0)).toBe("0 kg");
    expect(kg(0.004)).toBe("0 kg");
  });
  it("int groups thousands", () => expect(int(1350)).toBe("1,350"));
  it("shortDate reads like a calendar, in UTC (no timezone drift)", () => {
    expect(shortDate("2026-10-13")).toBe("Tue 13 Oct");
  });
  it("tsp rounds to kitchen fractions", () => {
    expect(tsp(4 / 3)).toBe("1⅓ tsp");
    expect(tsp(0.5)).toBe("½ tsp");
    expect(tsp(2)).toBe("2 tsp");
    expect(tsp(0.1)).toBe("<¼ tsp");
  });
  it("lineName", () => {
    expect(lineName("regular")).toBe("Pakcoy regular");
    expect(lineName("baby")).toBe("Pakcoy baby");
  });
});

describe("daySentence", () => {
  const base: TodayLine = {
    line: "regular", need_kg: 47, ceiling_kg: 42, send_kg: 42, short_kg: 5, rotated: ["Household 03"],
    sow: { day: "2026-10-15", weekday: "Thu", seedlings: 1350, seeds_g: 4.0, teaspoons: 4 / 3, shortfall_ahead_kg: 0 },
  };
  it("says who rotates when short", () => {
    expect(daySentence(base)).toBe(
      "Max safe tomorrow 42.0 kg · need 47.0 kg · short 5.00 kg → Household 03 rotates · Thu: sow 1,350 seedlings ≈ 4.0 g ≈ 1⅓ tsp",
    );
  });
  it("says send when nothing is short", () => {
    const ok = { ...base, need_kg: 37.17, ceiling_kg: 108.39, send_kg: 37.17, short_kg: 0, rotated: [] };
    expect(daySentence(ok)).toBe(
      "Send 37.2 kg tomorrow (max safe 108.4 kg) · Thu: sow 1,350 seedlings ≈ 4.0 g ≈ 1⅓ tsp",
    );
  });
  it("handles a day with no need", () => {
    const zero = { ...base, need_kg: 0, send_kg: 0, short_kg: 0, rotated: [] };
    expect(daySentence(zero)).toMatch(/^Nothing to send tomorrow · Thu: sow/);
  });
  it("mentions shortfall ahead", () => {
    const ahead = { ...base, short_kg: 0, rotated: [], sow: { ...base.sow, shortfall_ahead_kg: 12.5 } };
    expect(daySentence(ahead)).toMatch(/ · 12\.5 kg short ahead$/);
  });
});

describe("proposalLines", () => {
  it("orders", () => {
    const p = { ...empty, kind: "orders", orders: [{ buyer: "resto_a", line: "regular", kg: 15, day: "2026-10-13" }] } as Proposal;
    expect(proposalLines(p, state)).toEqual(["Restaurant A orders 15.0 kg Pakcoy regular for Tue 13 Oct"]);
  });
  it("harvest with and without sample", () => {
    const h = { ...empty, kind: "harvest", harvest: { bed: "Bed 41", batch: "b", kg: 11.5, big5_g: 620, small5_g: 310 } } as Proposal;
    expect(proposalLines(h, state)).toEqual(["Bed 41: harvested 11.5 kg · 5 biggest 620 g, 5 smallest 310 g"]);
    const h2 = { ...h, harvest: { ...h.harvest!, big5_g: null, small5_g: null } };
    expect(proposalLines(h2, state)).toEqual(["Bed 41: harvested 11.5 kg · no size sample"]);
  });
  it("sowing done and postponed", () => {
    const s = { ...empty, kind: "sowing", sowing: { line: "regular", postponed: false, seedlings: 1200, reason: "" } } as Proposal;
    expect(proposalLines(s, state)).toEqual(["Sowed 1,200 seedlings of Pakcoy regular today"]);
    const p = { ...s, sowing: { line: "baby", postponed: true, seedlings: null, reason: "heavy rain" } };
    expect(proposalLines(p, state)).toEqual(["Sowing of Pakcoy baby postponed: heavy rain"]);
  });
  it("loss", () => {
    const l = { ...empty, kind: "loss", loss: { bed: "Bed 2", batch: "b", pct: 30, cause: "caterpillars", cause_category: "pest" } } as Proposal;
    expect(proposalLines(l, state)).toEqual(["Bed 2: 30% of the plants lost (pest: caterpillars)"]);
  });
  it("signal", () => {
    const g = {
      ...empty, kind: "signal",
      signals: [{ scope: "buyer:resto_a", line: null, effect_pct: -50, date_from: "2026-10-19", date_to: "2026-10-25",
        open_ended: false, cause: "kitchen renovation", cause_category: "renovation" }],
    } as Proposal;
    expect(proposalLines(g, state)).toEqual(["Restaurant A, all lines: −50% from Mon 19 Oct to Sun 25 Oct (kitchen renovation)"]);
    const open = { ...g, signals: [{ ...g.signals[0], scope: "channel:B2C", effect_pct: 100, open_ended: true }] };
    expect(proposalLines(open, state)).toEqual(["Households, all lines: +100% from Mon 19 Oct onward (kitchen renovation)"]);
  });
  it("none and legacy/partial notes fall back to nothing (the card shows the summary)", () => {
    expect(proposalLines(empty, state)).toEqual([]);
    expect(proposalLines({ kind: "signal" } as unknown as Proposal, state)).toEqual([]);
    expect(proposalLines(undefined as unknown as Proposal, state)).toEqual([]);
  });
});

describe("scopeName", () => {
  it("names every scope", () => {
    expect(scopeName("all", state)).toBe("Everyone");
    expect(scopeName("channel:B2B", state)).toBe("Restaurants & caterers");
    expect(scopeName("channel:B2C", state)).toBe("Households");
    expect(scopeName("buyer:resto_a", state)).toBe("Restaurant A");
    expect(scopeName("buyer:ghost", state)).toBe("ghost");
  });
});

describe("friendly", () => {
  it("passes the API's own sentence through for 409 and 422", () => {
    expect(friendly(new ApiError(409, "the farm has moved on since this note was read; read it again")))
      .toBe("The farm has moved on since this note was read; read it again.");
    expect(friendly(new ApiError(422, "cannot apply this note (unknown batch)"))).toBe("Cannot apply this note (unknown batch).");
  });
  it("explains Gemini limits and failures", () => {
    expect(friendly(new ApiError(429, "x"))).toBe("Today's Gemini budget for this demo is used up. Try again tomorrow.");
    expect(friendly(new ApiError(502, "x"))).toBe("Gemini could not read the note just now. Try again in a moment.");
  });
  it("explains auth and network trouble", () => {
    expect(friendly(new ApiError(401, "x"))).toBe("Your demo session expired. Reload the page.");
    expect(friendly(new TypeError("Failed to fetch"))).toBe("Could not reach the server. Check the connection and retry.");
    expect(friendly("weird")).toBe("Something went wrong: weird");
  });
});
```

- [ ] **Step 5: Run them to see them fail**

Run: `cd frontend && npm test`
Expected: FAIL — `Failed to resolve import "./format"` (and `./api` has no `ApiError` yet).

- [ ] **Step 6: Write `types.ts` (replace the whole file)**

```ts
// Shapes of the API on feat/daily-engine. backend/tests/test_api_contract.py pins the same keys.

export type LineId = "regular" | "baby" | (string & {});
export type NoteKind = "orders" | "harvest" | "sowing" | "loss" | "signal" | "none";

export interface CropLine { id: LineId; min_g: number; max_g: number; channels: string[] }
export interface Crop {
  id: string; name: string; nursery_days: number; growth_curve: [number, number][]; spread_ratio: number;
  germination: number; survival: number; seeds_per_gram: number; grams_per_teaspoon: number; max_bed_day: number;
  max_seedlings_per_sowing: number; lines: CropLine[];
}
export interface Buyer {
  id: string; alias: string; segment: string; weekdays: number[];
  lines: Record<string, { kg: number; min_kg: number }>;
}
export interface Household { id: string; alias: string; line: LineId; kg: number; weekdays: number[] }
export interface Sender { id: string; alias: string }
export interface State {
  today: string; synthetic: boolean; crop: Crop; buyers: Buyer[]; households: Household[]; senders: Sender[];
}

export interface Signal {
  scope: string; line: LineId | null; effect_pct: number; date_from: string; date_to: string;
  open_ended?: boolean; cause: string; cause_category?: string;
}
export interface Proposal {
  kind: NoteKind; summary_en: string;
  orders: { buyer: string; line: LineId; kg: number; day: string }[];
  harvest: { bed: string; batch: string; kg: number; big5_g: number | null; small5_g: number | null } | null;
  sowing: { line: LineId; postponed: boolean; seedlings: number | null; reason: string } | null;
  loss: { bed: string; batch: string; pct: number; cause: string; cause_category: string } | null;
  signals: Signal[];
}
export interface NoteDoc {
  id: string; text: string; sender: string; received_on: string; proposal: Proposal; kind: NoteKind;
  summary_en: string; status: "proposed" | "no_action" | "accepted" | "rejected"; dropped: string[];
  model: string; cached: boolean; events?: unknown[];
}

export interface SowSummary {
  day: string; weekday: string; seedlings: number; seeds_g: number; teaspoons: number; shortfall_ahead_kg: number;
}
export interface TodayLine {
  line: LineId; need_kg: number; ceiling_kg: number; send_kg: number; short_kg: number; rotated: string[];
  sow: SowSummary;
}
export interface Today { today: string; weekday: string; lines: TodayLine[]; pending: NoteDoc[] }

export interface BatchRow {
  id: string; label: string; sown_on: string; bed_day: number; stage: "nursery" | "bed"; seedlings: number;
  plants_left: number; avg_g: number | null; offset_days: number; spread: number; sampled: boolean;
  ready_from: string; until: string; available_tomorrow_kg: number; waste_plants: number;
}
export interface ChartDay { day: string; available_kg: number; need_kg: number; short_kg: number }
export interface BedsLine { line: LineId; min_g: number; max_g: number; batches: BatchRow[]; chart: ChartDay[] }
export interface Beds { today: string; lines: BedsLine[] }

export interface DayKg { day: string; kg: number }
export interface TomorrowLine {
  line: LineId; day: string; need_kg: number; available_kg: number; ceiling_kg: number; send_kg: number;
  short_kg: number;
  buyers: { id: string; alias: string; known: boolean; ordered_kg: number; served_kg: number; min_kg: number }[];
  households: { id: string; alias: string; ordered_kg: number; served_kg: number }[];
  borrowing: DayKg[];
}
export interface Tomorrow { today: string; lines: TomorrowLine[] }

export interface SowLine {
  line: LineId; day: string; seedlings: number; seeds_g: number; teaspoons: number; ready_from: string;
  covers_until: string; gap_kg: number; capped: boolean; shortfall_ahead: DayKg[]; missed: string[];
  postponed: { day: string; reason: string }[];
  basis: { need: string; survival: number; germination: number; seeds_per_gram: number; grams_per_teaspoon: number;
    max_seedlings: number };
}
export interface Sow { today: string; lines: SowLine[] }

export interface DemandDay { day: string; low: number; expected: number; high: number; protected: number; target: number }
export interface Demand {
  today: string;
  market: { factor: number; buyers: number; text: string };
  series: { key: string; label: string; line: LineId; usual_kg: number; level_kg: number; shape: number[] }[];
  signals: (Signal & { t?: string })[];
  lines: { line: LineId; days: DemandDay[] }[];
}

export type Strategy = "cobweb" | "fixed" | "tanam";
export interface SeasonMetrics { waste_pct: number; b2b_fill_pct: number; hh_fill_pct: number; sowing_cv: number }
export interface Season {
  days: number; seeds: number[]; main_seed: number; synthetic: boolean;
  summary: Record<Strategy, SeasonMetrics>;
  runs: (SeasonMetrics & { strategy: Strategy; seed: number })[];
  sowings: Record<Strategy, { line: LineId; day: string; seedlings: number }[]>;
}

/** Everything the tabs need, refetched after every change (Season is loaded by its own tab). */
export interface Data { state: State; today: Today; beds: Beds; tomorrow: Tomorrow; sow: Sow; demand: Demand }
```

- [ ] **Step 7: Write `api.ts` (replace the whole file)**

```ts
import { idToken } from "./firebase";
import type { Beds, Demand, NoteDoc, Season, Sow, State, Today, Tomorrow } from "./types";

/** A non-2xx answer. `detail` is FastAPI's error text (plain English, written for people). */
export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`${status} ${detail}`);
  }
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { authorization: `Bearer ${await idToken()}` };
  if (body !== undefined) headers["content-type"] = "application/json";
  const res = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const d = JSON.parse(text).detail;
      detail = typeof d === "string" ? d : JSON.stringify(d);
    } catch {
      /* not JSON: keep the raw text */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  state: () => call<State>("/state"),
  today: () => call<Today>("/today"),
  beds: () => call<Beds>("/beds"),
  tomorrow: () => call<Tomorrow>("/tomorrow"),
  sow: () => call<Sow>("/sow"),
  demand: () => call<Demand>("/demand"),
  season: () => call<Season>("/season"),
  readNote: (text: string, sender: string) => call<NoteDoc>("/notes", { text, sender }),
  decideNote: (id: string, accept: boolean) => call<NoteDoc>(`/notes/${id}/${accept ? "accept" : "reject"}`, {}),
  nextDay: (from_day: string, days = 1) => call<{ today: string; appended: number }>("/day/next", { from_day, days }),
  reset: () => call<{ ok: boolean }>("/demo/reset", {}),
};
```

- [ ] **Step 8: Write `format.ts`**

```ts
import { ApiError } from "./api";
import type { LineId, Proposal, State, TodayLine } from "./types";

const DAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** 37.17 → "37.2 kg", 1.76 → "1.76 kg", 0 → "0 kg". */
export function kg(n: number): string {
  if (Math.abs(n) < 0.005) return "0 kg";
  return `${n.toFixed(Math.abs(n) >= 10 ? 1 : 2)} kg`;
}

export const int = (n: number) => Math.round(n).toLocaleString("en-US");

/** "2026-10-13" → "Tue 13 Oct". Parsed as UTC so the viewer's timezone never shifts the day. */
export function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return `${DAY[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
}

const FRACTIONS: [number, string][] = [[0, ""], [1 / 4, "¼"], [1 / 3, "⅓"], [1 / 2, "½"], [2 / 3, "⅔"], [3 / 4, "¾"], [1, ""]];

/** Teaspoons as a kitchen measure: 1.333 → "1⅓ tsp". Below ⅛ tsp → "<¼ tsp". */
export function tsp(x: number): string {
  if (x < 0.125) return "<¼ tsp";
  let whole = Math.floor(x);
  const [f, sym] = FRACTIONS.reduce((best, cur) => (Math.abs(cur[0] - (x - whole)) < Math.abs(best[0] - (x - whole)) ? cur : best));
  if (f === 1) whole += 1;
  return `${whole > 0 ? whole : ""}${f === 1 ? "" : sym}`.trim() + " tsp";
}

export const lineName = (id: LineId) => `Pakcoy ${id}`;

/** The one-line day summary from spec §10, per line. */
export function daySentence(l: TodayLine): string {
  const s = l.sow;
  const sow = `${s.weekday}: sow ${int(s.seedlings)} seedlings ≈ ${s.seeds_g.toFixed(1)} g ≈ ${tsp(s.teaspoons)}`;
  let head: string;
  if (l.need_kg < 0.005) head = "Nothing to send tomorrow";
  else if (l.short_kg > 0.005) {
    head = `Max safe tomorrow ${l.ceiling_kg.toFixed(1)} kg · need ${l.need_kg.toFixed(1)} kg · short ${kg(l.short_kg)}`;
    if (l.rotated.length) head += ` → ${l.rotated.join(", ")} ${l.rotated.length === 1 ? "rotates" : "rotate"}`;
  } else head = `Send ${kg(l.send_kg)} tomorrow (max safe ${kg(l.ceiling_kg)})`;
  const ahead = s.shortfall_ahead_kg > 0.005 ? ` · ${kg(s.shortfall_ahead_kg)} short ahead` : "";
  return `${head} · ${sow}${ahead}`;
}

export function scopeName(scope: string, state: State): string {
  if (scope === "all") return "Everyone";
  if (scope === "channel:B2B") return "Restaurants & caterers";
  if (scope === "channel:B2C") return "Households";
  const id = scope.replace(/^buyer:/, "");
  return state.buyers.find((b) => b.id === id)?.alias ?? id;
}

const pct = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n)}%`;

/** One plain line per proposed event. Unknown or partial (legacy) proposals give [] and the card
 *  falls back to the note's own summary. */
export function proposalLines(p: Proposal | undefined, state: State): string[] {
  if (!p) return [];
  const alias = (id: string) => state.buyers.find((b) => b.id === id)?.alias ?? id;
  switch (p.kind) {
    case "orders":
      return (p.orders ?? []).map((o) => `${alias(o.buyer)} orders ${kg(o.kg)} ${lineName(o.line)} for ${shortDate(o.day)}`);
    case "harvest": {
      const h = p.harvest;
      if (!h) return [];
      const sample = h.big5_g != null && h.small5_g != null
        ? `5 biggest ${h.big5_g} g, 5 smallest ${h.small5_g} g` : "no size sample";
      return [`${h.bed}: harvested ${kg(h.kg)} · ${sample}`];
    }
    case "sowing": {
      const s = p.sowing;
      if (!s) return [];
      return [s.postponed ? `Sowing of ${lineName(s.line)} postponed: ${s.reason || "no reason given"}`
        : `Sowed ${int(s.seedlings ?? 0)} seedlings of ${lineName(s.line)} today`];
    }
    case "loss": {
      const l = p.loss;
      return l ? [`${l.bed}: ${l.pct}% of the plants lost (${l.cause_category}: ${l.cause})`] : [];
    }
    case "signal":
      return (p.signals ?? []).map((s) => {
        const when = s.open_ended ? `from ${shortDate(s.date_from)} onward`
          : `from ${shortDate(s.date_from)} to ${shortDate(s.date_to)}`;
        return `${scopeName(s.scope, state)}, ${s.line ? lineName(s.line) : "all lines"}: ${pct(s.effect_pct)} ${when} (${s.cause})`;
      });
    default:
      return [];
  }
}

const sentence = (s: string) => {
  const t = s.trim();
  return t.charAt(0).toUpperCase() + t.slice(1) + (/[.!?]$/.test(t) ? "" : ".");
};

/** One sentence a visitor can act on, for any error the UI catches. */
export function friendly(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return "Your demo session expired. Reload the page.";
    if (e.status === 429) return "Today's Gemini budget for this demo is used up. Try again tomorrow.";
    if (e.status === 502) return "Gemini could not read the note just now. Try again in a moment.";
    return sentence(e.detail);
  }
  if (e instanceof TypeError) return "Could not reach the server. Check the connection and retry.";
  return `Something went wrong: ${e instanceof Error ? e.message : String(e)}`;
}
```

- [ ] **Step 9: Run the tests to green**

Run: `cd frontend && npm test`
Expected: all format tests PASS. (If `tsp(2)` gives `"2 tsp"` but `tsp(0.5)` gives `" ½ tsp"`, the `.trim()` is misplaced — it must wrap the joined number+fraction before `" tsp"`.)

- [ ] **Step 10: Local auth bypass in `firebase.ts`**

Replace the `idToken` export at the bottom with:

```ts
/** A fresh ID token (the SDK refreshes it before it expires). Local dev with NEXT_PUBLIC_AUTH=off
 *  skips Firebase entirely (the local API runs with AUTH=off and ignores the token), which also
 *  keeps headless screenshots from stalling on anonymous sign-in. */
export async function idToken(): Promise<string> {
  if (process.env.NEXT_PUBLIC_AUTH === "off") return "local";
  return (await user()).getIdToken();
}
```

`initializeApp`/`getAuth` at module load make no network call, so the module stays as is otherwise.

- [ ] **Step 11: Shell — `page.tsx` (replace the whole file), delete the weekly UI**

```bash
cd frontend && git rm -q components/CommitmentsTab.tsx components/ForecastTab.tsx components/InputsTab.tsx \
  components/LinePicker.tsx components/PlanTab.tsx components/ScenarioTab.tsx lib/series.ts
```

`frontend/app/page.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import { friendly, shortDate } from "@/lib/format";
import type { Data } from "@/lib/types";

export interface TabProps {
  data: Data;
  reload: () => Promise<void>;
}

interface Tab {
  id: string;
  label: string;
  hint: string;
  view: (p: TabProps) => ReactNode;
}

// Each later task adds its tab here, in spec order: Today, Beds, Tomorrow, Sow, Demand, Season.
const TABS: Tab[] = [];

export default function Home() {
  const [tab, setTab] = useState<string>("today");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [state, today, beds, tomorrow, sow, demand] = await Promise.all([
        api.state(), api.today(), api.beds(), api.tomorrow(), api.sow(), api.demand(),
      ]);
      setData({ state, today, beds, tomorrow, sow, demand });
    } catch (e) {
      setError(friendly(e));
    }
  }, []);

  useEffect(() => {
    const fromHash = window.location.hash.slice(1);
    if (TABS.some((t) => t.id === fromHash)) setTab(fromHash);
    load();
  }, [load]);

  const go = (id: string) => {
    setTab(id);
    history.replaceState(null, "", `#${id}`);
  };

  // A stale from_day (double click, second browser tab) appends nothing: reloading shows the real day.
  const advance = async (days: number) => {
    if (!data) return;
    setBusy(true);
    try {
      await api.nextDay(data.today.today, days);
      await load();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!window.confirm("Reset your demo farm to day 0? Your notes and simulated days are cleared.")) return;
    setBusy(true);
    try {
      await api.reset();
      await load();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  const i = Math.max(0, TABS.findIndex((t) => t.id === tab));
  const current = TABS[i];

  return (
    <main className="shell">
      <header className="top">
        <div>
          <h1>Tanam Secukupnya</h1>
          <p className="sub">Plant just enough: a daily planner that keeps a small farm out of the boom-and-bust cycle</p>
        </div>
        {data && (
          <div className="clock">
            <span>
              {data.today.weekday} <strong>{shortDate(data.today.today)}</strong>
            </span>
            {data.state.synthetic && <span className="pill muted">synthetic data</span>}
            <button className="primary" disabled={busy} onClick={() => advance(1)}>Next day →</button>
            <button disabled={busy} onClick={() => advance(7)}>+7 days</button>
            <button className="ghost" disabled={busy} onClick={reset}>Reset</button>
          </div>
        )}
      </header>

      <nav className="steps" aria-label="Tabs">
        {TABS.map((t, n) => (
          <button key={t.id} className={`step ${t.id === current?.id ? "on" : ""}`} onClick={() => go(t.id)}>
            <span className="num">{n + 1}</span>
            <span className="label">{t.label}</span>
          </button>
        ))}
      </nav>
      {current && <p className="hint">{current.hint}</p>}

      {error && (
        <div className="card error">
          {error}
          <button onClick={load}>Retry</button>
        </div>
      )}
      {!data && !error && <div className="card muted">Loading…</div>}
      {data && current && <section>{current.view({ data, reload: load })}</section>}

      {data && TABS.length > 1 && (
        <footer className="pager">
          <button disabled={i === 0} onClick={() => go(TABS[i - 1].id)}>← {i > 0 ? TABS[i - 1].label : ""}</button>
          <button disabled={i === TABS.length - 1} onClick={() => go(TABS[i + 1].id)}>
            {i < TABS.length - 1 ? TABS[i + 1].label : ""} →
          </button>
        </footer>
      )}
    </main>
  );
}
```

Append to `frontend/app/globals.css`:

```css
.clock { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
button.primary { background: var(--leaf); border-color: var(--leaf); color: #fff; font-weight: 600; }
button.primary:hover:not(:disabled) { filter: brightness(1.08); }
.sentence { font-size: 16px; line-height: 1.6; }
.empty { color: var(--muted); font-style: italic; padding: 8px 0; }
.bad { color: var(--bad); }
.legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 13px; color: var(--muted); margin-top: 6px; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
@media (max-width: 600px) {
  .clock { width: 100%; }
  .clock button.primary { flex: 1; }
}
```

In `layout.tsx` change the description to `"Plant just enough: a daily sowing and harvest planner for small farmers"`.

- [ ] **Step 12: Verify**

Run:
```bash
cd frontend && npm test && npx tsc --noEmit && npm run lint && npm run build
uv run --project backend pytest -q backend/tests
```
Expected: Vitest green; tsc/lint clean; `next build` succeeds (an empty tab list renders the header and clock only); pytest `171 passed` (163 + 8 contract).

- [ ] **Step 13: Commit**

```bash
git add -A frontend backend/tests/test_api_contract.py
git commit -m "feat(ui): daily-engine shell, API types + contract test, format helpers (Vitest)"
```

---

### Task 2: Today tab — day summary, note box, pending notes

**Files:**
- Create: `frontend/components/TodayTab.tsx`, `frontend/components/NoteCard.tsx`
- Modify: `frontend/app/page.tsx` (register the tab)

**Interfaces:**
- Consumes: `TabProps`, `api.readNote/decideNote`, `daySentence`, `proposalLines`, `friendly`, `lineName`, `Data.beds` (for example bed labels).
- Produces: `NoteCard` (props `{ note: NoteDoc; state: State; onDone: () => Promise<void> }`), reused by nothing else yet.

- [ ] **Step 1: Write `NoteCard.tsx`**

```tsx
"use client";

import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import { friendly, proposalLines, shortDate } from "@/lib/format";
import type { NoteDoc, State } from "@/lib/types";

/** A proposed note: what Gemini read, what was dropped, and Accept / Reject. If the farm moved on
 *  since it was read (409), offer to read the same text again. */
export default function NoteCard({ note, state, onDone }: { note: NoteDoc; state: State; onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; stale: boolean } | null>(null);
  const lines = proposalLines(note.proposal, state);
  const sender = state.senders.find((s) => s.id === note.sender)?.alias ?? note.sender;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await onDone();
    } catch (e) {
      setError({ text: friendly(e), stale: e instanceof ApiError && e.status === 409 });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="proposal">
      <p className="small muted">
        {sender} · {shortDate(note.received_on)} · <span className="pill">{note.kind}</span>
        {note.cached && <span className="pill muted">cached</span>}
      </p>
      <p className="small">“{note.text}”</p>
      {lines.length ? (
        <ul>{lines.map((l) => <li key={l}>{l}</li>)}</ul>
      ) : (
        <p>{note.summary_en}</p>
      )}
      {note.dropped?.length > 0 && <p className="small muted">Ignored: {note.dropped.join("; ")}</p>}
      {error && <p className="small bad">{error.text}</p>}
      <div className="row">
        {error?.stale ? (
          <button className="primary" disabled={busy}
            onClick={() => run(async () => {
              await api.decideNote(note.id, false);
              await api.readNote(note.text, note.sender);
            })}>
            Read again
          </button>
        ) : (
          <button className="primary" disabled={busy} onClick={() => run(() => api.decideNote(note.id, true))}>Accept</button>
        )}
        <button disabled={busy} onClick={() => run(() => api.decideNote(note.id, false))}>Reject</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write `TodayTab.tsx`**

Examples are built from the visitor's current beds so the harvest/loss notes always name a real bed.

```tsx
"use client";

import { useMemo, useState } from "react";

import NoteCard from "@/components/NoteCard";
import type { TabProps } from "@/app/page";
import { api } from "@/lib/api";
import { daySentence, friendly, lineName } from "@/lib/format";
import type { NoteDoc } from "@/lib/types";

export default function TodayTab({ data, reload }: TabProps) {
  const { state, today, beds } = data;
  const [text, setText] = useState("");
  const [sender, setSender] = useState("farmer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<NoteDoc | null>(null);

  const examples = useMemo(() => {
    const inBed = beds.lines[0]?.batches.filter((b) => b.stage === "bed" && b.plants_left > 0) ?? [];
    const ripe = inBed[0]?.label ?? "Bed 1";
    const young = inBed[inBed.length - 1]?.label ?? ripe;
    return [
      { sender: "resto_a", text: "Kak besok pakcoy 9 kilo ya, rabu 7 aja" },
      { sender: "farmer", text: `panen ${ripe.toLowerCase()} td pagi 11,5 kg. timbang 5 gede 620gr 5 kecil 310` },
      { sender: "farmer", text: `ulat nyerang ${young.toLowerCase()}, kira2 40% rusak` },
      { sender: "farmer", text: "hujan gede dr subuh, semai hari ini ga jadi bu" },
      { sender: "operator", text: "resto A mulai senin depan kurangi separo dulu, dapurnya renovasi 2 minggu" },
      { sender: "caterer_c", text: "makasih kak, transferan udah masuk ya" },
    ].filter((e) => state.senders.some((s) => s.id === e.sender));
  }, [beds, state.senders]);

  const read = async () => {
    setBusy(true);
    setError(null);
    setLast(null);
    try {
      const n = await api.readNote(text, sender);
      setLast(n);
      if (n.status === "proposed") setText("");
      await reload();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid two">
      <div className="card">
        <h2>{today.weekday}</h2>
        {today.lines.map((l) => (
          <div key={l.line} className="card">
            <h3>{lineName(l.line)}</h3>
            <p className={`sentence ${l.short_kg > 0.005 ? "bad" : ""}`}>{daySentence(l)}</p>
          </div>
        ))}
        <p className="small muted">
          Press <strong>Next day →</strong> to let the farm live one day: orders arrive, the farmer harvests and samples, and
          sowing happens on Mondays and Thursdays.
        </p>
      </div>

      <div className="card">
        <h2>Note from the field</h2>
        <p className="muted small">
          Paste a WhatsApp-style message. Gemini reads it into one farm event; nothing changes until you accept it.
        </p>
        <div className="row wrap">
          <label className="small">
            From{" "}
            <select value={sender} onChange={(e) => setSender(e.target.value)}>
              {state.senders.map((s) => <option key={s.id} value={s.id}>{s.alias}</option>)}
            </select>
          </label>
        </div>
        <textarea rows={3} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="e.g. panen bed 31 tadi 12 kg, 5 gede 650 gr 5 kecil 330" />
        <div className="row wrap">
          <button className="primary" disabled={busy || !text.trim()} onClick={read}>
            {busy ? "Reading…" : "Read with Gemini"}
          </button>
          <span className="small muted">Try:</span>
          {examples.map((e) => (
            <button key={e.text} className="ghost small" onClick={() => { setText(e.text); setSender(e.sender); }}>
              {e.text.length > 28 ? `${e.text.slice(0, 28)}…` : e.text}
            </button>
          ))}
        </div>
        {error && <p className="small bad">{error}</p>}
        {last && last.status === "no_action" && (
          <p className="small muted">No farm event in this note: {last.summary_en}</p>
        )}

        <h3>Waiting for you ({today.pending.length})</h3>
        {today.pending.length === 0 && <p className="empty">No notes waiting.</p>}
        {today.pending.map((n) => <NoteCard key={n.id} note={n} state={state} onDone={reload} />)}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Register the tab in `page.tsx`**

Add `import TodayTab from "@/components/TodayTab";` and set:

```tsx
const TABS: Tab[] = [
  { id: "today", label: "Today", hint: "The day in one line, and notes from the field", view: (p) => <TodayTab {...p} /> },
];
```

- [ ] **Step 4: Verify (types, build, real behavior)**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run build
```

Then with `just api` + `NEXT_PUBLIC_AUTH=off npx next dev -p 3100` running: `shot today 1200; shot today 390`, read both PNGs. Expected: header clock with Next day / +7 / Reset; two line cards with the sentence; note box. Press flow by hand in a browser (Windows: `http://localhost:3100`): Next day moves the date by one; a double-click still moves one day. A note needs Gemini (ADC) — if ADC is off locally, a 502 shows *“Gemini could not read the note just now…”* and the text stays in the box: that **is** the Review Focus #2 check.

- [ ] **Step 5: Commit**

```bash
git add frontend && git commit -m "feat(ui): Today tab — day summary, Gemini note box, accept/reject/read-again"
```

---

### Task 3: Beds tab

**Files:**
- Create: `frontend/components/BedsTab.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `Data.beds` (`BedsLine[]`), `kg`, `int`, `shortDate`, `lineName`.

- [ ] **Step 1: Write `BedsTab.tsx`**

```tsx
"use client";

import { Area, Bar, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TabProps } from "@/app/page";
import { int, kg, lineName, shortDate } from "@/lib/format";
import type { BedsLine } from "@/lib/types";

function LineBeds({ l }: { l: BedsLine }) {
  const shortDays = l.chart.filter((d) => d.short_kg > 0.005);
  const rows = l.batches.filter((b) => b.stage === "nursery" || b.plants_left > 0 || b.waste_plants > 0);
  return (
    <div className="card">
      <h2>{lineName(l.line)} <span className="muted small">sells at {l.min_g}–{l.max_g} g a plant</span></h2>
      <p className="small muted">
        Next 40 days: kg ready in range each day vs. the need we protect (B2B expected + households low).
        {shortDays.length > 0 && <span className="bad"> {shortDays.length} day(s) short.</span>}
      </p>
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <ComposedChart data={l.chart.map((d) => ({ ...d, label: shortDate(d.day) }))}>
            <XAxis dataKey="label" interval={6} tick={{ fontSize: 11 }} />
            <YAxis width={40} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v: number) => kg(v)} />
            <Area dataKey="available_kg" name="Ready" fill="var(--leaf-soft)" stroke="var(--leaf)" />
            <Line dataKey="need_kg" name="Need" stroke="var(--soil)" dot={false} strokeWidth={2} />
            <Bar dataKey="short_kg" name="Short" fill="var(--bad)" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="legend">
        <span><i style={{ background: "var(--leaf)" }} />ready</span>
        <span><i style={{ background: "var(--soil)" }} />need</span>
        <span><i style={{ background: "var(--bad)" }} />short</span>
      </div>

      <h3>Batches ({rows.length})</h3>
      {rows.length === 0 ? (
        <p className="empty">Nothing in the nursery or the beds for this line.</p>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Bed</th><th>Sown</th><th className="num">Bed day</th><th className="num">Plants left</th>
                <th className="num">Avg g</th><th className="num">Growth</th><th>Ready</th>
                <th className="num">Tomorrow</th><th className="num">Wasted</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.id}>
                  <td>{b.label}{b.stage === "nursery" && <span className="pill muted">nursery</span>}</td>
                  <td>{shortDate(b.sown_on)}</td>
                  <td className="num">{b.bed_day}</td>
                  <td className="num">{int(b.plants_left)}</td>
                  <td className="num">{b.avg_g ?? "—"}</td>
                  <td className="num" title={b.sampled ? "from the farmer's 5+5 sample" : "crop default"}>
                    {b.offset_days > 0 ? "+" : ""}{b.offset_days} d{b.sampled ? " ✓" : ""}
                  </td>
                  <td>{shortDate(b.ready_from)} – {shortDate(b.until)}</td>
                  <td className="num">{kg(b.available_tomorrow_kg)}</td>
                  <td className={`num ${b.waste_plants > 0 ? "neg" : ""}`}>{int(b.waste_plants)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="small muted">
        Growth: days ahead (+) or behind (−) the crop curve; ✓ = corrected by a harvest sample. Quick field estimate: assumes
        sizes spread evenly between the small and big groups.
      </p>
    </div>
  );
}

export default function BedsTab({ data }: TabProps) {
  return <div className="grid">{data.beds.lines.map((l) => <LineBeds key={l.line} l={l} />)}</div>;
}
```

- [ ] **Step 2: Register** — `import BedsTab from "@/components/BedsTab";` and append to `TABS`:
  `{ id: "beds", label: "Beds", hint: "What is growing, and how much is ready each day", view: (p) => <BedsTab {...p} /> },`
  Add `.grid { display: grid; gap: 16px; }` to `globals.css` (`.grid.two` already exists and still wins for two-column).

- [ ] **Step 3: Verify** — `npx tsc --noEmit && npm run lint && npm run build`; `shot beds 1200; shot beds 390`; read both. Expected: two cards with a 40-day chart and a batch table that scrolls sideways inside the card at 390 px (no page scroll). Done batches with nothing left and no waste are hidden.

- [ ] **Step 4: Commit** — `git add frontend && git commit -m "feat(ui): Beds tab — 40-day ready-vs-need chart and batch table"`

---

### Task 4: Tomorrow tab

**Files:**
- Create: `frontend/components/TomorrowTab.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `Data.tomorrow` (`TomorrowLine[]`), `kg`, `shortDate`, `lineName`.

- [ ] **Step 1: Write `TomorrowTab.tsx`**

```tsx
"use client";

import type { TabProps } from "@/app/page";
import { kg, lineName, shortDate } from "@/lib/format";
import type { TomorrowLine } from "@/lib/types";

function LineTomorrow({ l }: { l: TomorrowLine }) {
  const short = l.short_kg > 0.005;
  return (
    <div className="card">
      <h2>{lineName(l.line)} · {shortDate(l.day)}</h2>
      <div className="kpis">
        <div><span className="small muted">Need</span><strong>{kg(l.need_kg)}</strong></div>
        <div><span className="small muted">Ready in range</span><strong>{kg(l.available_kg)}</strong></div>
        <div><span className="small muted">Max safe to send</span><strong>{kg(l.ceiling_kg)}</strong></div>
        <div><span className="small muted">Send</span><strong className={short ? "bad" : ""}>{kg(l.send_kg)}</strong></div>
      </div>
      <p className="small muted">
        Max safe = the most we can pick tomorrow without making any later day (until the next sowing is ready) shorter than
        it would be anyway.
      </p>
      {short && <p className="bad">Short {kg(l.short_kg)}: B2B minimums first, the rest pro-rata; households that were shorted least recently rotate out.</p>}

      <h3>Restaurants & caterers</h3>
      {l.buyers.length === 0 ? <p className="empty">No B2B orders for this line.</p> : (
        <div className="scroll">
          <table>
            <thead><tr><th>Buyer</th><th className="num">Ordered</th><th className="num">Minimum</th><th className="num">Served</th></tr></thead>
            <tbody>
              {l.buyers.map((b) => (
                <tr key={b.id}>
                  <td>{b.alias} {!b.known && <span className="pill muted" title="no order yet: the forecast stands in">forecast</span>}</td>
                  <td className="num">{kg(b.ordered_kg)}</td>
                  <td className="num">{kg(b.min_kg)}</td>
                  <td className={`num ${b.served_kg < b.ordered_kg - 0.005 ? "neg" : ""}`}>{kg(b.served_kg)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>Households</h3>
      {l.households.length === 0 ? <p className="empty">No household deliveries tomorrow.</p> : (
        <ul className="signals">
          {l.households.map((h) => {
            const out = h.served_kg < h.ordered_kg - 0.005;
            return (
              <li key={h.id}>
                <span className={`pill ${out ? "down" : "up"}`}>{out ? (h.served_kg > 0 ? "partly" : "rotates out") : "served"}</span>{" "}
                {h.alias} <span className="muted small">{kg(h.served_kg)} of {kg(h.ordered_kg)}</span>
              </li>
            );
          })}
        </ul>
      )}

      {l.borrowing.length > 0 && (
        <>
          <h3>If we sent the full need anyway</h3>
          <p className="small muted">Picking more than the safe maximum borrows from later days:</p>
          <ul>{l.borrowing.map((b) => <li key={b.day} className="bad">borrowing from {shortDate(b.day)}: −{kg(b.kg)}</li>)}</ul>
        </>
      )}
    </div>
  );
}

export default function TomorrowTab({ data }: TabProps) {
  return <div className="grid">{data.tomorrow.lines.map((l) => <LineTomorrow key={l.line} l={l} />)}</div>;
}
```

- [ ] **Step 2: Register** — import and append
  `{ id: "tomorrow", label: "Tomorrow", hint: "The most we can safely send, and who gets it", view: (p) => <TomorrowTab {...p} /> },`

- [ ] **Step 3: Verify** — tsc, lint, build; `shot tomorrow 390`. Expected: baby card shows “No B2B orders for this line.” (Review Focus #4); regular lists 4 buyers and 6 households, all “served” on day 0.

- [ ] **Step 4: Commit** — `git commit -am "feat(ui): Tomorrow tab — safe ceiling, who is served or rotated, borrowing view"`

---

### Task 5: Sow tab

**Files:**
- Create: `frontend/components/SowTab.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `Data.sow` (`SowLine[]`), `int`, `kg`, `tsp`, `shortDate`, `lineName`.

- [ ] **Step 1: Write `SowTab.tsx`**

```tsx
"use client";

import type { TabProps } from "@/app/page";
import { int, kg, lineName, shortDate, tsp } from "@/lib/format";
import type { SowLine } from "@/lib/types";

function LineSow({ s }: { s: SowLine }) {
  const ahead = s.shortfall_ahead.reduce((a, r) => a + r.kg, 0);
  return (
    <div className="card">
      <h2>{lineName(s.line)} · sow on {shortDate(s.day)}</h2>
      <div className="kpis">
        <div><span className="small muted">Seedlings</span><strong>{int(s.seedlings)}</strong></div>
        <div><span className="small muted">Seed</span><strong>≈ {s.seeds_g.toFixed(1)} g</strong></div>
        <div><span className="small muted">Measure</span><strong>≈ {tsp(s.teaspoons)}</strong></div>
        <div><span className="small muted">Ready</span><strong>{shortDate(s.ready_from)} – {shortDate(s.covers_until)}</strong></div>
      </div>
      <table>
        <tbody>
          <tr><td>Gap this batch must fill</td><td className="num">{kg(s.gap_kg)}</td></tr>
          <tr><td>Need used</td><td className="num">{s.basis.need}</td></tr>
          <tr><td>Seedlings that make it to harvest</td><td className="num">{Math.round(s.basis.survival * 100)}%</td></tr>
          <tr><td>Seeds that germinate</td><td className="num">{Math.round(s.basis.germination * 100)}%</td></tr>
          <tr><td>Seeds per gram · grams per teaspoon</td><td className="num">{s.basis.seeds_per_gram} · {s.basis.grams_per_teaspoon}</td></tr>
        </tbody>
      </table>
      {s.capped && <p className="bad">Capped at the farm's limit of {int(s.basis.max_seedlings)} seedlings per sowing.</p>}
      {(s.missed.length > 0 || s.postponed.length > 0) && (
        <>
          <h3>Missed sowings</h3>
          <ul>
            {s.postponed.map((p) => <li key={p.day}>{shortDate(p.day)}: postponed ({p.reason})</li>)}
            {s.missed.filter((d) => !s.postponed.some((p) => p.day === d)).map((d) => <li key={d}>{shortDate(d)}: no sowing recorded</li>)}
          </ul>
          <p className="small muted">This sowing grows to cover what the missed batch would have covered.</p>
        </>
      )}
      {ahead > 0.005 && (
        <>
          <h3 className="bad">Short ahead: {kg(ahead)}</h3>
          <p className="small muted">Days no sowing can reach in time any more (even picking 3 days early or late):</p>
          <ul>{s.shortfall_ahead.map((r) => <li key={r.day}>{shortDate(r.day)}: {kg(r.kg)}</li>)}</ul>
        </>
      )}
    </div>
  );
}

export default function SowTab({ data }: TabProps) {
  return (
    <div className="grid">
      <p className="muted small">We sow twice a week, on Mondays and Thursdays. Each sowing covers the days until the next one is ready.</p>
      {data.sow.lines.map((s) => <LineSow key={s.line} s={s} />)}
    </div>
  );
}
```

- [ ] **Step 2: Register** — import and append
  `{ id: "sow", label: "Sow", hint: "How many seedlings on the next sowing day, and why", view: (p) => <SowTab {...p} /> },`

- [ ] **Step 3: Verify** — tsc, lint, build; `shot sow 390`. Then in the browser accept the “hujan … semai ga jadi” example on a Monday (needs ADC) or skip if Gemini is off locally; the API-level behaviour is already covered by `test_postponed_sowing_note_lands_on_the_next_sow_day`.

- [ ] **Step 4: Commit** — `git commit -am "feat(ui): Sow tab — next sowing with breakdown, missed sowings, shortfall ahead"`

---

### Task 6: Season tab

**Files:**
- Create: `frontend/components/SeasonTab.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `api.season()`, `Season`, `shortDate`, `int`.

- [ ] **Step 1: Write `SeasonTab.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TabProps } from "@/app/page";
import { api } from "@/lib/api";
import { friendly, int, shortDate } from "@/lib/format";
import type { Season, SeasonMetrics, Strategy } from "@/lib/types";

const NAMES: Record<Strategy, string> = { cobweb: "Cobweb farmer", fixed: "Fixed farmer", tanam: "Tanam Secukupnya" };
const RULES: Record<Strategy, string> = {
  cobweb: "Sows more after a short week, less after a surplus week",
  fixed: "The same seedlings every Monday and Thursday",
  tanam: "This app: sows to the forecast, harvests up to the safe maximum",
};
const COLORS: Record<Strategy, string> = { cobweb: "var(--bad)", fixed: "var(--warn)", tanam: "var(--leaf)" };
const ORDER: Strategy[] = ["cobweb", "fixed", "tanam"];
const METRICS: { key: keyof SeasonMetrics; label: string; better: "low" | "high"; fmt: (n: number) => string }[] = [
  { key: "waste_pct", label: "Waste", better: "low", fmt: (n) => `${n.toFixed(1)}%` },
  { key: "b2b_fill_pct", label: "Restaurant orders filled", better: "high", fmt: (n) => `${n.toFixed(1)}%` },
  { key: "hh_fill_pct", label: "Household orders filled", better: "high", fmt: (n) => `${n.toFixed(1)}%` },
  { key: "sowing_cv", label: "Swing in sowing (CV)", better: "low", fmt: (n) => n.toFixed(2) },
];

export default function SeasonTab(_: TabProps) {
  const [s, setS] = useState<Season | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.season().then(setS).catch((e) => setError(friendly(e)));
  }, []);
  if (error) return <div className="card error">{error}</div>;
  if (!s) return <div className="card muted">Loading the season…</div>;
  if (!s.runs.length) return <div className="card empty">The season comparison has not been computed (run `just season`).</div>;

  const range = (st: Strategy, k: keyof SeasonMetrics) => {
    const v = s.runs.filter((r) => r.strategy === st).map((r) => r[k]);
    return [Math.min(...v), Math.max(...v)] as const;
  };
  const days = Array.from(new Set(ORDER.flatMap((st) => s.sowings[st].filter((x) => x.line === "regular").map((x) => x.day)))).sort();
  const chart = days.map((d) => {
    const row: Record<string, string | number> = { day: shortDate(d) };
    for (const st of ORDER) {
      const hit = s.sowings[st].find((x) => x.line === "regular" && x.day === d);
      if (hit) row[st] = hit.seedlings;
    }
    return row;
  });

  return (
    <div className="grid">
      <div className="card">
        <h2>{Math.round(s.days / 7)} weeks, three ways to farm</h2>
        <p className="small muted">
          The same simulated farm and buyers, run {s.seeds.length} times with different random seeds. Mean shown, range across
          runs below. Synthetic data; Gemini is not in this loop.
        </p>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Strategy</th>{METRICS.map((m) => <th key={m.key} className="num">{m.label}</th>)}</tr>
            </thead>
            <tbody>
              {ORDER.map((st) => (
                <tr key={st}>
                  <td><strong style={{ color: COLORS[st] }}>{NAMES[st]}</strong><br /><span className="small muted">{RULES[st]}</span></td>
                  {METRICS.map((m) => {
                    const [lo, hi] = range(st, m.key);
                    return (
                      <td key={m.key} className="num">
                        <strong>{m.fmt(s.summary[st][m.key])}</strong><br />
                        <span className="small muted">{m.fmt(lo)}–{m.fmt(hi)}</span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h2>Seedlings per sowing (pakcoy regular, seed {s.main_seed})</h2>
        <p className="small muted">The cobweb farmer swings; the fixed farmer never adapts; Tanam follows demand.</p>
        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer>
            <LineChart data={chart}>
              <XAxis dataKey="day" interval={7} tick={{ fontSize: 11 }} />
              <YAxis width={48} tick={{ fontSize: 11 }} tickFormatter={(v: number) => int(v)} />
              <Tooltip formatter={(v: number) => int(v)} />
              <Legend />
              {ORDER.map((st) => (
                <Line key={st} dataKey={st} name={NAMES[st]} stroke={COLORS[st]} dot={false} strokeWidth={2} connectNulls />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Register** — import and append
  `{ id: "season", label: "Season", hint: "Six months, three strategies: does it actually waste less?", view: (p) => <SeasonTab {...p} /> },`
  (Season stays last; Task 7 inserts Demand **before** it.)

- [ ] **Step 3: Verify** — tsc, lint, build; `shot season 1200; shot season 390`. Expected: 3 rows with 52.6 / 34.5 / 13.0 waste and their ranges; a chart with three lines.

- [ ] **Step 4: Commit** — `git commit -am "feat(ui): Season tab — three strategies over 26 weeks, 5 seeds"`

---

### Task 7: Demand tab

**Files:**
- Create: `frontend/components/DemandTab.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `Data.demand`, `scopeName`, `kg`, `shortDate`, `lineName`.

- [ ] **Step 1: Write `DemandTab.tsx`**

```tsx
"use client";

import { Area, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TabProps } from "@/app/page";
import { kg, lineName, scopeName, shortDate } from "@/lib/format";

export default function DemandTab({ data }: TabProps) {
  const { demand, state } = data;
  return (
    <div className="grid">
      <div className="card">
        <h2>Market</h2>
        <p className={demand.market.factor !== 1 ? "bad" : ""}>{demand.market.text}</p>
        <p className="small muted">
          Recomputed every day from the last 7 days of restaurant orders. It moves every forecast, including buyers who haven't
          ordered yet and households.
        </p>
      </div>

      {demand.lines.map((l) => (
        <div key={l.line} className="card">
          <h2>{lineName(l.line)}: next {l.days.length} days</h2>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <ComposedChart data={l.days.map((d) => ({ ...d, label: shortDate(d.day), band: [d.low, d.high] }))}>
                <XAxis dataKey="label" interval={6} tick={{ fontSize: 11 }} />
                <YAxis width={40} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v: number | number[]) => (Array.isArray(v) ? `${kg(v[0])} – ${kg(v[1])}` : kg(v))} />
                <Area dataKey="band" name="Low–high" fill="var(--leaf-soft)" stroke="none" />
                <Line dataKey="expected" name="Expected" stroke="var(--leaf)" dot={false} strokeWidth={2} />
                <Line dataKey="target" name="Sowing target" stroke="var(--sky)" dot={false} strokeDasharray="4 3" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="legend">
            <span><i style={{ background: "var(--leaf-soft)" }} />band (80%)</span>
            <span><i style={{ background: "var(--leaf)" }} />expected</span>
            <span><i style={{ background: "var(--sky)" }} />sowing target (B2B high + households high)</span>
          </div>
        </div>
      ))}

      <div className="card">
        <h2>Buyers: usual vs. now</h2>
        <p className="small muted">The weekday shape is fixed; only the level moves. Three orders in a row on the same side move it fast.</p>
        <div className="scroll">
          <table>
            <thead><tr><th>Series</th><th>Line</th><th className="num">Usual / day</th><th className="num">Now / day</th></tr></thead>
            <tbody>
              {demand.series.map((s) => {
                const d = s.level_kg - s.usual_kg;
                const moved = Math.abs(d) > 0.1 * Math.max(s.usual_kg, 0.01);
                return (
                  <tr key={s.key}>
                    <td>{s.label}</td>
                    <td>{s.line}</td>
                    <td className="num">{kg(s.usual_kg)}</td>
                    <td className={`num ${moved && d < 0 ? "neg" : ""}`}>{kg(s.level_kg)} {moved ? (d < 0 ? "↓" : "↑") : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>Accepted signals</h2>
        {demand.signals.length === 0 ? <p className="empty">None yet. A note like “bulan depan pesanan dobel” becomes one.</p> : (
          <ul className="signals">
            {demand.signals.map((s, i) => (
              <li key={i}>
                <span className={`pill ${s.effect_pct < 0 ? "down" : "up"}`}>{s.effect_pct > 0 ? "+" : ""}{s.effect_pct}%</span>{" "}
                {scopeName(s.scope, state)}, {s.line ? lineName(s.line) : "all lines"}{" "}
                <span className="muted small">{shortDate(s.date_from)} – {shortDate(s.date_to)} · {s.cause}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Register** — import and insert **before** the Season entry:
  `{ id: "demand", label: "Demand", hint: "Forecast per day with an honest band, and what moved it", view: (p) => <DemandTab {...p} /> },`
  Final order must be Today, Beds, Tomorrow, Sow, Demand, Season.

- [ ] **Step 3: Verify** — tsc, lint, build; `shot demand 1200`. Then press **+7 days** five times (to ~week 10 where the truth world's −15% market drop starts) and re-shoot: expected the market line to switch from “No market-wide move” to “Market −1x% across N buyers…”. If it never switches by week 12, note it in the ledger as a finding for the founder (do not tune).

- [ ] **Step 4: Commit** — `git commit -am "feat(ui): Demand tab — band chart, buyer levels, market factor, signals"`

---

### Task 8: The video's shortfall moment exists (engine check, no UI)

**Files:**
- Create: `backend/tests/test_demo_story.py`

**Interfaces:**
- Consumes: the API with `fake_gemini` (same pattern as `backend/tests/test_api.py`).

- [ ] **Step 1: Write the test**

```python
"""The demo video needs one visible shortfall: a pest hits the ripest regular bed, and within a few
days Tomorrow shows a ceiling below the need, a household rotating out, or shortfall ahead on Sow.
If this fails, the engine is fine but the story is not: bring it to the founder, don't tune."""

from fastapi.testclient import TestClient

from app import gemini, main
from app.notes import LossReading, NoteReading

client = TestClient(main.app)


def test_a_pest_on_the_ripest_bed_shows_up_as_a_shortfall_story(monkeypatch):
    client.post("/api/demo/reset")
    try:
        today = client.get("/api/state").json()["today"]
        ripe = [b for b in client.get("/api/beds").json()["lines"][0]["batches"]
                if b["stage"] == "bed" and b["available_tomorrow_kg"] > 0]
        for b in ripe[:2]:  # the two beds feeding the next days
            monkeypatch.setattr(gemini, "read_note", lambda *a, _b=b, **k: {"model": "fake", "reading": NoteReading(
                kind="loss", summary_en="pest", loss=LossReading(bed=_b["label"], pct=80, cause="caterpillars",
                                                                 cause_category="pest"))})
            n = client.post("/api/notes", json={"text": f"ulat {b['label']} 80%", "sender": "farmer"}).json()
            assert client.post(f"/api/notes/{n['id']}/accept").status_code == 200
        seen = []
        for _ in range(7):
            t = client.get("/api/today").json()["lines"][0]
            seen.append((t["short_kg"], t["ceiling_kg"] < t["need_kg"], bool(t["rotated"]), t["sow"]["shortfall_ahead_kg"]))
            if t["short_kg"] > 0 or t["sow"]["shortfall_ahead_kg"] > 0:
                break
            client.post("/api/day/next", json={"from_day": today})
            today = client.get("/api/state").json()["today"]
        assert any(s[0] > 0 or s[3] > 0 for s in seen), f"no shortfall within 7 days: {seen}"
    finally:
        client.post("/api/demo/reset")
```

- [ ] **Step 2: Run it**

Run: `uv run --project backend pytest -q backend/tests/test_demo_story.py`
Expected: PASS. **If it fails**, stop the plan here and report the printed `seen` list to the founder with two options in prose: (a) the video uses a bigger event (e.g. a postponed sowing *and* a pest), (b) the seed beds are rebalanced so the farm starts closer to its need. Do not change engine code in this plan.

- [ ] **Step 3: Commit** — `git add backend/tests/test_demo_story.py && git commit -m "test: the demo's shortfall moment (pest on the ripest beds) shows up within a week"`

---

### Task 9: Re-seed Firestore and deploy — **FOUNDER GATE**

**Files:**
- Modify: `scripts/seed_firestore.py`, `justfile`

**Interfaces:**
- Consumes: `app.store.{COLLECTIONS, WORKSPACE, FirestoreStore, JsonStore, load_seed}`.

- [ ] **Step 0: STOP and ask the founder** — in plain prose: “The UI is ready on `feat/daily-engine`. Deploying means: merge to main, wipe old visitor workspaces and the weekly collections in Firestore, push the new API and UI. The live weekly app goes away. Go?” Do nothing below until they say yes.

- [ ] **Step 1: Teach the seed script to remove the weekly app's leftovers**

In `scripts/seed_firestore.py`, add after `BATCH = 400`:

```python
# The weekly app's reference collections and workspace subcollections. Plan 2 removes them once.
OBSOLETE = ("farmers", "partners", "orders")
OLD_WORKSPACE = ("signals", "runs", "notes", "events")


def delete_all(db, refs) -> int:
    refs = list(refs)
    for k in range(0, len(refs), BATCH):
        b = db.batch()
        for r in refs[k:k + BATCH]:
            b.delete(r)
        b.commit()
    return len(refs)


def wipe_old(db) -> None:
    """Drop obsolete reference collections and every visitor workspace (old notes have the weekly
    proposal shape the daily UI cannot render; visitors simply start at day 0 again)."""
    for c in OBSOLETE:
        print(f"{c}: deleted {delete_all(db, (d.reference for d in db.collection(c).stream()))} (obsolete)")
    n = 0
    for user in db.collection("users").list_documents():  # includes uids that only have subcollections
        for c in OLD_WORKSPACE:
            n += delete_all(db, (d.reference for d in user.collection(c).stream()))
    print(f"users/*: deleted {n} workspace docs")
```

Change the `main` signature and the `__main__` block:

```python
def main(project: str = "tanam-secukupnya", wipe: bool = False) -> None:
    db = firestore.Client(project=project)
    if wipe:
        wipe_old(db)
    ...  # existing body unchanged


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--wipe-workspaces"]
    main(*args, wipe="--wipe-workspaces" in sys.argv)
```

In `justfile`, under `seed-firestore`, add a second recipe:

```
# One-off for the daily-engine launch: also delete the weekly app's collections and ALL visitor workspaces
seed-firestore-fresh:
    uv run --project backend python scripts/seed_firestore.py --wipe-workspaces
```

- [ ] **Step 2: Merge to main** (founder said yes)

```bash
git checkout main && git pull --ff-only && git merge --no-ff feat/daily-engine -m "Merge feat/daily-engine: daily pakcoy engine + six-tab UI"
uv run --project backend pytest -q backend/tests && (cd frontend && npm test && npm run build)
git push
```

Expected: all green; then `gh run list --branch main -L 1` shows the backend CI run succeeding.

- [ ] **Step 3: Re-seed (needs ADC on tanam-secukupnya; founder runs `gcloud auth application-default login` if it fails)**

```bash
uv run --project backend python scripts/seed_firestore.py --wipe-workspaces
```

Expected: `farmers/partners/orders: deleted N (obsolete)`, `users/*: deleted N`, one line per collection in `COLLECTIONS`, `round-trip OK`. The live weekly API is broken from here until Step 4 finishes — do Step 4 immediately.

- [ ] **Step 4: Deploy (the `just deploy` lines, by hand)**

```bash
P=tanam-secukupnya R=asia-southeast2
gcloud builds submit --config cloudbuild.yaml --project $P \
  --service-account projects/$P/serviceAccounts/tanam-build@$P.iam.gserviceaccount.com
gcloud run deploy tanam-api --image $R-docker.pkg.dev/$P/tanam/api:latest --region $R --project $P \
  --update-env-vars STORE=firestore,AUTH=on
(cd frontend && npm run build)
firebase deploy --only hosting --project $P
curl -fsS https://$P.web.app/api/health && echo
test "$(curl -s -o /dev/null -w '%{http_code}' https://$P.web.app/api/today)" = 401 && echo "auth required: OK"
```

Expected: a new Cloud Run revision serving 100%; `{"ok":true}`; `auth required: OK`. `--no-invoker-iam-check` set earlier persists across deploys; if the API answers 403 at the Cloud Run layer, the founder re-runs it (the classifier blocks Claude from doing so).

- [ ] **Step 5: Live check**

Cloud Run logs after the founder opens the site on their phone:
```bash
gcloud run services logs read tanam-api --region asia-southeast2 --project tanam-secukupnya --limit 40
```
Expected: `GET /api/state|today|beds|tomorrow|sow|demand` 200s, `POST /api/day/next` 200. Ask the founder to: press Next day twice, read one example note, accept it, open every tab. Headless Edge stalls on anonymous sign-in, so the phone check is the real one.

- [ ] **Step 6: Commit + push the seed script**

```bash
git add scripts/seed_firestore.py justfile && git commit -m "chore(seed): one-off wipe of the weekly app's collections and workspaces" && git push
```

---

### Task 10: README and REPORT (Sunday)

**Files:**
- Rewrite: `README.md`
- Create: `REPORT.md`

- [ ] **Step 1: Gather the numbers** (never retype them by hand from memory)

```bash
python3 -c "import json;s=json.load(open('data/seed/season.json'));print(json.dumps(s['summary'],indent=1))"
head -20 eval/results/g1-dev-gemini-3.5-flash.md eval/results/g1-holdout-gemini-3.5-flash.md
uv run --project backend pytest -q backend/tests | tail -1
(cd frontend && npm test 2>&1 | tail -3)
```

- [ ] **Step 2: Rewrite `README.md`** with these sections, in this order, all English, aliases only:
  1. Title + one-line pitch (*Plant just enough: a daily planner that keeps a small farm out of the boom-and-bust cycle*) + live URL + “Built for the Google Cloud AI Builder Cup 2026 — Sustainability & Social Impact”.
  2. **The problem** (3 sentences: the cobweb cycle; small farmers plant too much after a shortage and too little after a glut; waste and missed orders).
  3. **What it does every day**: the three answers (what is on the beds, max safe to send tomorrow, seedlings to sow next) and the four inputs diagram from spec §1, verbatim.
  4. **Results**: the season table (three strategies; waste, B2B fill, household fill, sowing CV; mean and range over 5 seeds × 182 days) from Step 1, and G1 accuracy (dev 60/60 after one tuning round, holdout 18/18 written after tuning and run once).
  5. **Where Gemini is used, and where it isn't** (reads notes into one of six event kinds; a person accepts every one; the engine itself is deterministic arithmetic, so a mistake is visible and correctable).
  6. **How it runs on Google Cloud**: update the existing diagram (`users/{uid}/{notes,events}`; reference data crops, buyers, households, batches, history).
  7. **Run it locally**: the commands table (keep `just test`, `just api`, `just eval`, `just season`, `just seed-firestore`, `just deploy`; add `cd frontend && npm test`).
  8. **Data and honesty**: synthetic data, generated from real field experience; notes and labels written by Claude and reviewed by the founder; no real people or businesses.
  9. **Roadmap**: spec §13 list.

- [ ] **Step 3: Write `REPORT.md`** (the technical write-up for judges):
  1. Design decisions D1–D10 table (copy from the spec §2).
  2. Engine: production model (curve, uniform spread, readiness), demand model (shape × level × market × signals, the band formula), the three outputs and how each search works (binary search for ceiling and seedlings).
  3. Evaluation: the season method (truth world, 3 strategies, metrics, 5 seeds) and its numbers; G1 method (dev/holdout split, one tuning round, the two prompt rules added, tokens ~3,600 in / ~90 out per note, median 6.7 s) and its numbers.
  4. Limitations, honestly: synthetic data; uniform size spread is a quick field estimate; stock isn't tracked (sold by the next day); the five deferred minors from the Plan 1 final review, in plain words.
  5. Cost: Gemini cached by input and capped per day; the engine costs nothing to run.

- [ ] **Step 4: Secret scan before the repo goes public**

```bash
git grep -nE "AIza|BEGIN (RSA|OPENSSH)|private_key|ya29\.|-----BEGIN" -- . ':!frontend/lib/firebase.ts' || echo "clean"
git log -p --all | grep -nE "ya29\.|private_key\"|BEGIN (RSA|OPENSSH) PRIVATE" | head || true
```

Expected: `clean` and no log hits. (The Firebase web `apiKey` in `firebase.ts` is public by design and stays.)

- [ ] **Step 5: Commit** — `git add README.md REPORT.md && git commit -m "docs: README and REPORT for the daily engine" && git push`

- [ ] **Step 6: Ask the founder** (prose): set Cloud Run `--min-instances 1` for judging week (removes the ~3 s cold start; costs roughly the price of one small instance kept warm until judging ends), and flip the repo to public with an MIT license. Do neither without a yes.

---

### Task 11 (optional — first to cut): G5 “Why?” on Today

Only if Tasks 1–9 are deployed and it is before Saturday 20:00.

**Files:**
- Modify: `backend/app/gemini.py`, `backend/app/main.py`, `backend/tests/test_api.py`, `frontend/lib/api.ts`, `frontend/components/TodayTab.tsx`

**Interfaces:**
- Produces: `gemini.explain(today: dict, tomorrow: dict, sow: dict) -> {"text": str, "model": str}`; `POST /api/today/why -> {"text": str, "model": str, "cached": bool}`; `api.why()`.

- [ ] **Step 1: Failing API test** (append to `backend/tests/test_api.py`)

```python
def test_why_narrates_the_engine_numbers_and_is_cached(monkeypatch):
    seen = []

    def explain(today, tomorrow, sow):
        seen.append(today["today"])
        return {"text": "Because the beds hold enough.", "model": "fake"}
    monkeypatch.setattr(gemini, "explain", explain)
    a = client.post("/api/today/why").json()
    b = client.post("/api/today/why").json()
    assert a["text"] == "Because the beds hold enough." and not a["cached"] and b["cached"]
    assert seen == ["2026-10-12"]
```

Run: `uv run --project backend pytest -q backend/tests/test_api.py -k why` → FAIL (404).

- [ ] **Step 2: Implement**

`backend/app/gemini.py`, append:

```python
G5_SYSTEM = """You explain a small farm's daily plan to a busy farmer and to hackathon judges. You get the
engine's own numbers as JSON. Narrate them in 3–5 short plain-English sentences: what to send tomorrow and
why that is the safe maximum, who is short if anyone, and why the next sowing is that size. Use only numbers
that appear in the JSON; never compute new ones; never give advice the JSON does not support."""


def explain(today: dict, tomorrow: dict, sow: dict) -> dict:
    import json

    from google.genai import types

    r = _generate(
        model=MODEL,
        contents=json.dumps({"today": today, "tomorrow": tomorrow, "sow": sow}, ensure_ascii=False),
        config=types.GenerateContentConfig(system_instruction=G5_SYSTEM, temperature=0),
    )
    return {"text": (r.text or "").strip(), "model": r.model_version or MODEL}
```

`backend/app/main.py`, after `read_note`:

```python
_g5_cache: dict[str, dict] = {}


@api.post("/today/why")
def why(ws: Store = Depends(workspace)) -> dict:
    """G5: Gemini narrates today's numbers from the engine's own JSON (computes nothing)."""
    t, tm, sw = farm.today(ws), farm.tomorrow(ws), farm.sow(ws)
    t = {k: v for k, v in t.items() if k != "pending"}
    key = hashlib.sha256(json.dumps([t, tm, sw], sort_keys=True).encode()).hexdigest()
    if key in _g5_cache:
        return {**_g5_cache[key], "cached": True}
    _spend_one_call()
    try:
        out = gemini.explain(t, tm, sw)
    except Exception as e:
        raise HTTPException(502, f"Gemini could not explain the day ({type(e).__name__}).") from e
    _g5_cache[key] = out
    return {**out, "cached": False}
```

Add `import json` at the top of `main.py`, and `main._g5_cache.clear()` to the `fresh` fixture in `test_api.py`.

Run: `uv run --project backend pytest -q backend/tests` → all pass.

- [ ] **Step 3: UI** — `api.ts`: `why: () => call<{ text: string; model: string; cached: boolean }>("/today/why", {}),`. In `TodayTab.tsx`, under the line cards:

```tsx
const [why, setWhy] = useState<string | null>(null);
// …
<button disabled={busy} onClick={async () => {
  setWhy("Asking Gemini…");
  try { setWhy((await api.why()).text); } catch (e) { setWhy(friendly(e)); }
}}>Why?</button>
{why && <p className="small">{why}</p>}
```

Reset `why` to `null` whenever `today.today` changes (`useEffect(() => setWhy(null), [today.today])`).

- [ ] **Step 4: Verify** — tsc, lint, build; with ADC, press Why? once locally and read the text against the Today numbers (every number it says must appear on screen).

- [ ] **Step 5: Commit** — `git commit -am "feat(g5): Why? — Gemini narrates today's plan from the engine's numbers"`; deploy only with the founder (Task 9 Step 4 again).
