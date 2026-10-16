# Sandbox + two-layer growth calibration — design

Date: 2026-10-15 · Status: agreed in conversation; written spec awaiting founder review ·
Builds on: [daily engine](2026-10-14-daily-engine-design.md) (same engine, same event log).

## 1. Why

The demo is good for showing, but too much of it is pre-made: a hidden "world" invents the
sales, the growth and the pests, so the cause → effect is hard to follow. The founder wants a
**blank farm** where they set the growth curve and the demand themselves, then enter what happens
**day by day** and watch the decisions move. Judges can use it too, and clear it again.

At the same time the founder corrected how a bed that grows badly should be modelled (§5):
a stunted bed (most often from planting too densely) **stays small**, it does not just run late.
That change applies to the whole engine, demo included.

## 2. Decisions (founder, 2026-10-15)

| # | Decision |
|---|---|
| S1 | A new page **`/sandbox`** in the same app, on the **same engine**. The demo stays as it is (apart from S5). |
| S2 | Each visitor gets their own empty sandbox, with a **Clear** button. There is no hidden world: **the visitor is the world**. |
| S3 | Setup (crop table, buyers) is edited **in the app**, with a live curve chart, and accepts **copy-paste from Google Sheets** (tab-separated). No Sheets API. |
| S4 | A starting demand estimate per buyer is **optional** (what the buyer says they usually order). The engine starts with a wide band and learns from real orders. |
| S5 | **Model B everywhere:** a bed's own curve is the reference curve **scaled by a percentage** (same shape, smaller or bigger). Replaces the "N days late" offset. |
| S6 | The **reference curve** learns **per age node**, slowly, only from healthy sampled beds. |
| S7 | Daily input is **free text → Gemini → a formatted confirmation → saved only on OK**. A plain form is the fallback. |
| S8 | Prototype honesty: this is a **calibration loop**, not reinforcement learning. RL in simulation is roadmap (pitch deck: calibration loop → per-season curves → RL in simulation). |
| S9 | All UI text is English (it is shown to judges). |

## 3. Pages and data

- `/sandbox` is a separate route with its own tabs: **Setup · Today · Beds · Tomorrow · Sow · Demand · Trail**.
  Today/Beds/Tomorrow/Sow/Demand reuse the demo's tab components on sandbox data.
- Storage: a separate workspace per visitor, `users/{uid}/sandbox/...` (Firestore in prod, JsonStore
  locally), holding `setup` (one doc) and the event `log`. Same event-sourced replay as the demo.
- **Clear** deletes the sandbox log and setup and returns to Setup.
- API: the demo routes are mirrored under `/api/sandbox/...` (`state, today, beds, tomorrow, sow,
  demand, trail, setup (GET/PUT), events (POST), notes, notes/{id}/accept|reject, day/next, clear`).
  One code path: the routes take a `mode` that picks the workspace and whether a world exists.

## 4. Setup

**Crop table** (one crop, pakcoy defaults pre-filled, every field editable):
`nursery_days`, `growth_curve` points (bed day → g/plant, strictly increasing), `spread_ratio`,
`germination`, `survival`, `max_bed_day`, `lines` (id, min_g, max_g, channels),
`seeds_per_gram`, `grams_per_teaspoon`, `sow_weekdays` (default Mon + Thu).
The chart redraws while editing; invalid input (non-increasing curve, min ≥ max) is shown inline
and blocks Save.

**Buyers:** name, type (`business` or `household`), line, optional `usual_kg_per_week`,
optional order weekdays, and `min_kg` for businesses. Names are whatever the visitor types (the
repo-public alias rule applies to seed data, not to what a visitor enters).

**Start:** a start date (default today, WIB) and optional existing beds (line, sown date,
seedlings), so a real farm can start mid-cycle. An empty field is allowed.

**Copy-paste:** each table has "Paste from sheet" (tab- or comma-separated rows with a header
row) and "Copy as sheet".

**Editing setup later** re-runs the whole event log on the new setup (replay is cheap), so the
visitor sees the effect at once. *Stretch, first to cut:* a side-by-side "old setup vs new" trail.

## 5. Growth calibration — two layers (model B)

**Layer 1 — the bed's own curve.** Every batch has `size_factor` (default 1.0):
`avg_g(bed, day) = size_factor × reference(day)`. Same shape, scaled. A harvest sample
(5 biggest + 5 smallest weighed together) gives the average `a` at bed day `t`:
`size_factor = a / reference(t)`, clamped to [0.5, 1.5]; the sample also sets the bed's spread,
as now. A stunted bed therefore reaches the line's minimum later, or never, and tops out smaller.
`growth_offset_days` and `MAX_OFFSET` are removed.

**Layer 2 — the reference curve.** It changes **only at the nodes near the sampled age**:
- A sample at bed day `t` between nodes `x₀ ≤ t ≤ x₁` is a candidate for both nodes, with
  weights by distance (`w₁ = (t − x₀)/(x₁ − x₀)`, `w₀ = 1 − w₁`).
- Each node keeps its last 5 candidate ratios `a / reference(t)` from **healthy** beds. A bed
  with a recorded loss/pest event is not healthy and never feeds the reference.
- On each new candidate the node moves toward the **median** of its kept ratios:
  `y ← y × (1 + clamp(0.3 × (median − 1) × w, −5 %, +5 %))`.
  The median is the "many beds" rule: one stunted bed barely moves it; when most recent beds
  agree, the node follows.
- After a move, nodes are made strictly increasing again (each node at least the previous + 1 g),
  and the sampled bed's `size_factor` is recomputed against the new reference, so its own
  projection still equals what was weighed.
- The starting curve is kept; the UI shows reference vs starting curve per node with a sample
  count, and a "Reset reference" action (a logged event, so replay stays exact).

Both layers live in state rebuilt by replay, so they are deterministic from the log. Because the
reference changes, the crop object used for a projection is rebuilt whenever the reference moves
(the production cache is keyed by crop identity, so this stays correct).

**Demo impact (S5).** The demo world's truth becomes a per-batch size factor (instead of offset
days); its sample generator uses it. The Season numbers in `data/seed/season.json`, the demo
story test and G5 checks are re-run, and any README/REPORT figure comes from the new file.

## 6. Demand in the sandbox

- A buyer's series starts from `usual_kg_per_week` spread evenly over their order weekdays
  (all 7 if none given), with sigma = 50 % of that level, so the band starts wide. No estimate →
  level 0 until the first order.
- The weekday shape is the declared weekdays (D7 still holds: shape fixed, level learns).
- An **order** is (buyer, line, day, kg). When **Next day** closes a day, each buyer's orders
  for that day become that series' actual (0 if a regular weekday passed with no order), and the
  level learns exactly as in the demo. Households are aggregated per line, as in the demo.
- The market factor needs ≥ 3 business buyers to move; with fewer it stays 1.0 (shown).

## 7. Daily input

**Gemini path (S7).** One text box ("Restaurant A orders 12 kg for tomorrow, harvested bed 3,
20 kg, biggest five 640 g, smallest five 410 g"). Gemini (existing G1 reader, given the sandbox's
buyer names, bed ids and today's date) returns typed events. The UI shows a **confirmation card**
in a fixed format, one line per event, e.g.
`ORDER · Restaurant A · regular · 12.0 kg · Fri 16 Oct` /
`HARVEST · Bed 3 · 20.0 kg · sample 640 g / 410 g`.
Nothing is stored until **OK**; **Edit** opens the form pre-filled; **Discard** drops it.
Unknown buyer or bed names are flagged on the card, never guessed.

**Form path.** Same event kinds, one small form each: order, sow (line, seedlings, day),
harvest (bed, kg, optional sample), loss (bed or all beds of a line, %, cause), signal
(buyer or all, factor, from–to, reason), postpone sowing.

**Next day** closes the day: orders become actuals (§6); if no harvest was logged for a bed today,
the engine assumes the planned send was harvested oldest-first (as the demo does); logged
harvests replace that assumption for the day.

## 8. Decision trail

One row per sandbox day, newest first: date · forecast tomorrow (low–high) · ready kg · safe
ceiling · send · short · next sowing (date, seedlings) · reference curve change (if any) ·
the inputs logged that day. A cell that changed versus the previous row because of that day's
input is highlighted. Rows are computed by replaying the log up to each day (cached per day).

## 9. Errors and limits

- Gemini daily cap and the shared per-instance budget apply to sandbox notes too.
- Event validation is shared with the demo (`check_events`); a bad event is a 422 with a message
  the UI shows next to the form.
- Max 400 sandbox days and 50 buyers per visitor (stops runaway replay cost).

## 10. Testing

- Unit: size-factor sample math; reference node update (weights, median, ±5 % cap, monotonic
  repair, healthy-only, sampled bed re-anchored); cold-start demand (estimate, none, weekdays);
  order → actual on day close; setup validation.
- API: sandbox isolation from the demo and between users; clear; setup edit re-runs the log;
  Gemini confirm flow (stubbed Gemini) stores nothing before OK.
- Regression: full backend suite, demo story test and Season re-run under model B.
- Gemini: a small sandbox eval (~15 notes with visitor-style names, English and Bahasa) run once
  and reported honestly.

## 11. Cut order if time runs short

1. Side-by-side old-vs-new setup trail.
2. Existing beds at start (start empty only).
3. Gemini path (form only) — last, since it is the "plus" for judges.
