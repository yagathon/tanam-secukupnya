# Daily engine — design

Date: 2026-10-14 · Status: approved in conversation; written spec awaiting review ·
Replaces: the weekly planner (`planner.py`), the Commitments and Harvest scenario tabs.

## 1. Why

The first prototype had one input: notes that nudge a weekly forecast. That isn't how a farm
runs. A farm runs **daily**, and it learns from **four inputs**: two on the production side and
two on the demand side. Each side has a model and a daily sample that corrects it. The output is
what a farmer actually needs to decide every day:

1. how much is still on the beds
2. the most we can send tomorrow **without breaking the cycle**
3. how many seedlings to sow on the next sowing day

The rhythm we aim for is **sowing twice a week (fixed days) and harvesting every day**.

```
PRODUCTION                                DEMAND
(1) growth model (crop table)             (3) demand model (shape × level × market)
(2) today's harvest + size sample         (4) today's actual orders
            └────────────── daily engine ──────────────┘
                 a. beds: harvestable per day ahead
                 b. max safe to send tomorrow (+ who is served / rotated)
                 c. seedlings to sow on the next sowing day
```

## 2. Decisions (made with the founder, 2026-10-14)

| # | Decision |
|---|---|
| D1 | Approach A: replace the weekly core with **one daily engine**. Do not layer it on top of the weekly one. |
| D2 | **Pakcoy first.** Sawi putih comes later and only needs its growth curve and windows in the crop table, with no engine change. |
| D3 | The planning unit is the **seedling**. Seed grams and teaspoons are shown as conversions. |
| D4 | Sowing happens on **fixed days (Mon + Thu)**. A missed or postponed sowing is "pending": the next sowing absorbs the shortfall, and the gap it leaves is flagged as a shortfall ahead. |
| D5 | Order timing is mixed (C): **tomorrow's need = known B2B orders + household forecast**. Harvested stock is not tracked: what is harvested on a day is sold by the next day. The 2-day shelf buffer is on the roadmap. |
| D6 | Harvest sample: the farmer weighs the **5 biggest together** and the **5 smallest together**. The app derives the averages, the growth offset and the spread. |
| D7 | Demand: the weekday **shape is fixed**. Only the **level** moves (per buyer, plus a shared market factor). Learning a shape that slowly changes with behaviour is roadmap ("RL"). |
| D8 | Everything enters as a **WhatsApp-style note** read by Gemini. A person Accepts or Rejects it before anything changes. |
| D9 | A **"Next day →"** demo clock per visitor, plus a **Season** tab comparing strategies over 26 weeks. |
| D10 | The repo goes public: **no real customer names**. Use aliases ("Restaurant A", "Household 03"). |

## 3. Crop table (pakcoy)

The existing `crops.json` profile shape is extended; values are synthetic and disclosed.

| Field | Pakcoy default | Meaning |
|---|---|---|
| `nursery_days` | 15 | sowing → transplant |
| `growth_curve` | `[[0,5],[7,15],[14,45],[18,70],[21,100],[24,125],[27,145],[30,160]]` | (bed day, grams/plant), piecewise-linear, strictly increasing so it can be inverted |
| `spread_ratio` | 0.45 | prior size spread before any sample: (big avg − small avg) / avg |
| `germination` | 0.85 | seed → seedling |
| `survival` | 0.90 | seedling → plant that makes it to harvest (transplant losses + baseline pests) |
| `seeds_per_gram` | 400 | display only |
| `grams_per_teaspoon` | 3 | display only |
| `max_bed_day` | 30 | anything still in the bed after this is waste |
| `lines` | `regular`: 100–140 g, B2B + B2C · `baby`: 50–70 g, B2C | acceptable weight range per demand line |

One batch per line (the founder's rule). Cross-filling between lines is a harvest-day decision
only and is never planned.

## 4. Production model

**Batch:** `{id, crop, line, sown_on, seedlings, status: nursery|bed|done|lost, growth_offset_days
(default 0), spread_ratio (default crop prior), harvested_plants, lost_plants}`.
`plants0 = seedlings × survival`.

**Weight on a day:** `bed_day = date − (sown_on + nursery_days)`, `eff_day = bed_day +
growth_offset_days`, `avg_g = curve(eff_day)`. Plant weights are modelled as **uniform** on
`[avg·(1 − r/2), avg·(1 + r/2)]` with `r = spread_ratio`.

**Readiness, cumulatively** (we always harvest the biggest in-range plants first):
- `F_ready(t)` = share of plants with weight ≥ the line's minimum
- `F_over(t)` = share above the line's maximum, or 1 after `max_bed_day`
- `waste_cum(t) = max(0, plants0·F_over(t) − harvested_cum − lost)`, i.e. plants that grew past
  the range without being picked
- `available(t) = max(0, plants0·F_ready(t) − harvested_cum − waste_cum(t) − lost)`
- kg = plants × the mean weight of the in-range part of the distribution

**Harvest sample** `{batch, kg_harvested, big5_g_total, small5_g_total}`:
- `big = big5/5`, `small = small5/5`, `avg = (big + small)/2`, `r = (big − small)/avg`
- `growth_offset_days = curve⁻¹(avg) − bed_day` (clamped to ±7)
- `harvested_plants += kg_harvested·1000 / avg`
- On screen: *"quick field estimate: assumes sizes spread evenly between the small and big
  groups."*

**Loss note:** `lost_plants += pct × plants still in bed`.

## 5. Demand model (per day)

**Series:** one per B2B buyer × line, plus one pooled **households** series per line.

`expected(series, d) = shape[weekday(d)] × level(series) × market(d) × Π signal factors`

- **shape:** each series' weekday profile (mean by weekday ÷ overall mean) from history, **fixed**
  (D7).
- **market factor `m`:** recomputed daily from the last 7 days of B2B orders. For each buyer,
  ratio = actual ÷ (shape × level). `m` = the median ratio, applied only when ≥ 3 buyers have
  orders, ≥ 60% of them are on the same side of 1, and |m − 1| ≥ 5%. Otherwise `m = 1`.
  `m` applies to **every** series, including buyers who haven't ordered yet and households.
  Shown as *"Market −15% across 5 buyers this week (cause unknown)."*
- **level (idiosyncratic):** exponential smoothing of `actual ÷ (shape × m)` with α = 0.2. When
  the **last 3 residuals share a sign** and each exceeds 0.5σ, that update uses α = 0.6 (shift
  detection). Because the level is fitted on demand with `m` already divided out, the market
  drop is not counted twice. Shown as *"Restaurant A: usual 6.0 kg → now 4.2 kg ↓ (3 orders
  below usual)."*
- **band:** σ of one-step residuals; low/high = expected ∓ 1.28·σ·√(1+(h−1)α²) (same maths as
  the current `forecast.py`, applied per day).
- **signals:** accepted demand-signal notes with a known cause, kept as today (a factor over a date
  range and a scope).

**Needs used by the engine:**
- **tomorrow:** known B2B orders (when present, else the B2B expected) + households expected
- **protected future day:** B2B expected + households **low**
- **sowing target:** B2B **high** + households **high**

## 6. Engine outputs

All three run one deterministic day-by-day **projection** per line:
`project(batches, needs_by_day, tomorrow_harvest_override?) → per day {available, harvested,
short, waste}`. Each day it serves the need from batches **oldest first**.

**a. Beds:** each batch row (age, plants left, offset ±days, spread, ready-from/until), plus a
40-day chart of available kg against protected need, with shortfall days in red.

**b. Max safe to send tomorrow (per line):**
- Horizon = tomorrow through the **first ready day of the next sowing's batch** (≈ 36 days for
  pakcoy).
- `ceiling` = the largest tomorrow harvest `x ≤ available(tomorrow)` such that the total
  projected shortfall over the horizon is no worse than at `x = 0`. Found by binary search over
  `x`.
- If tomorrow's need > ceiling, the allocator (reused, now per day) decides who is served: B2B
  minimums first, the rest pro-rata, and households rotate by "shorted least recently".
- **Borrowing view:** when the need is above the ceiling, project at `x = need` and list the days
  whose shortfall grows (*"borrowing from 18 Nov: −3 kg"*).

**c. Sow next (per line):**
- Next sowing day = the next Mon/Thu that is today or later.
- Coverage = from that batch's first ready day until the following sowing's first ready day.
- `seedlings` = the smallest count (step 50) whose added batch makes every coverage day **that the
  batch can reach** shortfall-free against the **sowing target** need. Found by binary search with
  `project`, capped at the farm's capacity (`max_seedlings_per_sowing` in the crop table, default
  3,000). Days the batch can't reach, and anything above the cap, are reported as shortfall ahead
  and never make the search diverge.
- Shown with the breakdown (gap kg, band used, survival) and the conversions: `seeds_g =
  seedlings / germination / seeds_per_gram`, teaspoons = `seeds_g / grams_per_teaspoon`.
- **Postponed/pending:** a missed Mon/Thu means that batch doesn't exist. The next sowing's
  coverage then starts at the missed batch's first ready day, so the recommendation grows. The
  days nobody can reach any more (even with ±3 days early or late) show as **shortfall ahead**,
  and because they fall inside (b)'s horizon, the ceiling tightens from today.

## 7. Notes (Gemini)

One endpoint reads a Bahasa note and returns one of these kinds. Fields are validated by the
existing sanitize-then-score pattern, and nothing is applied until Accept.

| Kind | Example | Extracted |
|---|---|---|
| `orders` | "Resto A besok pakcoy 8 kg, baby 2 kg" | buyer, line, kg, for date |
| `harvest` | "Bedeng 3 panen 14 kg, 5 terbesar 650 g, 5 terkecil 330 g" | batch or bed, kg, big5 total, small5 total |
| `sowing` | "semai 1.200 bibit pakcoy reguler" / "Kamis hujan, semai ditunda" | line, seedlings, or postponed + reason |
| `loss` | "ulat, kira-kira 30% bedeng 2 rusak" | batch, pct, cause |
| `signal` | "bulan depan resto buka cabang, pesanan dobel" | scope, effect %, date range, cause (as G1 today) |
| `none` | chit-chat | — |

**Eval:** regenerate the labeled set to about 10 dev notes per kind and 3 held-out notes per
kind. They are Claude-written and disclosed, and the founder reviews them for realism. `just
eval` reports kind accuracy and field accuracy. The old 15/15 number is retired, not reused.

**G5 (optional):** a "Why?" button on Today. Gemini explains the day's numbers from the engine's
own breakdown JSON. It narrates only and computes nothing.

## 8. State, demo clock, data

- **Truth world** (hidden, generated, deterministic seed): 8 weeks of daily history before demo
  day 0, plus 26 weeks ahead. It holds:
  - true daily demand per series, including a market drop of −15% from week 10, Restaurant A's
    slow decline, and households
  - true growth offset per batch (±2 days)
  - rain on 2 sowing days
  - one pest event
- **Visitor state = seed + an ordered event log** under `users/{uid}/events` (accepted notes and
  simulated days). The engine state is rebuilt by **replaying** the log. It's deterministic and
  cheap at demo scale, and Reset just clears the log.
- **"Next day →"** appends the day's events from the truth world:
  - B2B orders for tomorrow
  - household actuals
  - the harvest actually done, with its 5+5 sample
  - on Mon/Thu, the recommended sowing, unless rain or a user "postponed" note blocks it
  - pest events
- Every visitor sees the same world, which makes the video reproducible.
- Reference data in Firestore is re-seeded with the daily dataset (`scripts/seed_firestore.py`).

## 9. Season simulation

The same truth world and the same day loop, run for 26 weeks under three strategies:

| Strategy | Sowing rule |
|---|---|
| Cobweb farmer | next sowing = last sowing × (1 + 0.5·last week's shortage %) or × (1 − 0.5·last week's surplus %) |
| Fixed farmer | the same seedlings every Mon/Thu (the 8-week historical average) |
| Tanam Secukupnya | the engine's (c), and harvests capped by (b) |

**Metrics:** waste % (plants that grew past the range or were left unsold), B2B fill rate,
household fill rate, and swing in sowing (CV of seedlings per sowing). We run 5 seeds and report
a range: *"waste 31% → 9%"*. Gemini is not in the loop: note accuracy is reported separately by
`just eval`. Results are precomputed at seed time and also runnable via the API. They're shown in
a **Season** tab.

## 10. API and UI

**API** (`/api/health` open; everything else needs auth as today):
- `GET /state`: clock, crops, buyers
- `GET /today`: the one-line day summary and pending notes
- `GET /beds`, `GET /tomorrow`, `GET /sow`, `GET /demand`
- `POST /notes`, `POST /notes/{id}/accept|reject`
- `POST /day/next`
- `POST /demo/reset`
- `GET /season`

**UI tabs:**
1. **Today:** note box plus the day summary (*"Max safe tomorrow 42 kg · need 47 kg · short 5 kg →
   Household 03 rotates · Thu: sow 1,350 seedlings ≈ 4.0 g ≈ 1⅓ tsp"*), the "Next day →" button
   and Reset.
2. **Beds**
3. **Tomorrow**
4. **Sow**
5. **Demand**
6. **Season**

Removed: Commitments, Sowing plan (weekly), Harvest scenario, and the weekly `planner.py` /
`run_plan` / `run_scenario`. `crops.py` zones are replaced by the growth curve plus line weight
ranges. `allocator.py` is reused per day.

## 11. Testing

Unit tests, pure, no cloud:
- curve interpolation and its inverse
- sample → offset/spread/plants
- cumulative ready/over/waste accounting
- projection oldest-first
- ceiling: none borrowed when there's no gap; tightens when a sowing is pending
- sowing sizing: the coverage window is closed; postponement grows the next sowing
- demand:
  - the shape stays fixed
  - one low order moves the level a little, three move it a lot
  - the market factor applies to unseen buyers and isn't counted twice
- replay determinism: same log → same state
- Next day is idempotent per day index

Plus API tests with `AUTH=off`, `just eval` for Gemini, and a season sim smoke test (Tanam's
waste is below cobweb's on the default seed).

## 12. Schedule and cut order

| When | Build |
|---|---|
| Wed 14 evening | crop table, production model, demand model, projection, outputs (a)(b)(c), daily truth-world generator, tests |
| Thu 15 evening | event log + replay, API, Gemini note kinds, new eval set, Next day |
| Fri 16 evening | 6 tabs UI, re-seed Firestore, deploy, founder phone check |
| Sat 17 → 20:00 | season sim + tab, G5 if time, polish, **feature freeze** |
| Sun 18 | video ~3:10 (rules: 3–4 min), deck content, README, REPORT.md, secret scan, min-instances 1, submit |

**Cut order if behind:** G5 → sawi putih → `loss` note kind → market factor.
**Never cut:** harvest sample, orders, Today/Beds/Tomorrow/Sow, Next day, season simulation.

## 13. Roadmap (for the deck, not built)

- the 2-day shelf buffer
- shapes that adapt to slow behaviour change (RL in simulation)
- sawi putih and more crops
- WhatsApp send-out (G3/G4)
- multi-farmer allocation
- weather-aware sowing
