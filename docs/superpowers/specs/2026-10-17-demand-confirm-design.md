# Demand learning: confirm before changing — design

Date: 2026-10-17 · Branch: `feat/demand-confirm` (from `fix/sandbox-uat`) · Status: awaiting founder review

## Why

On Thu 26 Nov in the founder's sandbox log the sowing advice jumped from 350 to 850 seedlings after one
ordinary order (Resto WKS, 4 kg). Two causes:

1. **Daily learning reacts too fast.** The month-end season factor (0.8) made three steady 4 kg orders
   read as 5 kg. The "3 same-sign residuals" shift rule then moved the level at α 0.6, from 5.62 to 6.41 (+14%).
   Even +5% moved the advice 350 → 800: a month of slightly higher demand empties the old beds before the
   new batch is ready.
2. **Sowing targets the high scenario** ("B2B high + households high", the 80% band). That is
   "never run short" thinking.

The founder's principles (2026-10-17):

- **Waste hurts more than a shortfall.** A shortfall is covered from the market while the farm is small.
- **A 3-day rise or a one-off order must not change the forecast.**
- **A change counts only once confirmed:** 3 weeks for a weekly change, several months for the
  month pattern.
- **Target "pas":** expected demand, no buffer scenario.

## Rules

### A. Level: checked at week end, moves after 3 confirming weeks

- At the end of each calendar week (Mon–Sun, when the Sunday is processed), for each series:
  - `A` = the sum of actuals that week, over days with a known actual;
  - `F` = the sum of forecasts for the same days, `shape × level × season × market`, with the level as
    it stood that week.
  - Ratio `q = A / F`.
  - `q > 1.10` → the week is **above**; `q < 0.90` → **below**; otherwise **normal**.
  - A week whose Monday is before the first history day gives no verdict (a Saturday start must not make
    Sat–Sun a whole "week above"; found by the year-end replay).
  - In practice the check compares implied week levels: (season- and market-divided actual sum) ÷
    (weekday-shape sum) against the level. When season and market are constant over the week this is
    `A/F`. A level at 0 judges any orders as "above", so a series confirmed down to 0 can come back.
- The verdict is on the week's **total**. Daily ups and downs inside the week do not matter.
- **3 consecutive weeks in the same direction** → `level ← level × mean(q of those 3 weeks)`. Then the
  streak resets.
  - A normal week, or a week in the other direction, resets the streak.
  - Up and down are symmetric (founder: no asymmetry).
- Removed:
  - the daily EWMA level update (`ALPHA`);
  - the 3-day shift rule (`ALPHA_SHIFT`).
- Kept:
  - the daily residuals, used only for σ (the band and the protected floor);
  - the start rules: setup prior, first order sets the level when no estimate, history init for the
    demo world;
  - `usual` (the level 14 days ago).
- **Market factor: unchanged** (out of scope).
  - It needs ≥3 buyers, so the single-buyer sandbox never triggers it.
  - The demo world relies on it.

### B. Month pattern: checked at month end, farm-wide, moves after 3 confirming months

- Applies only when a season is set (sandbox). The demo world has no season.
- Only calendar months covered from day 1 to the last day count. The sandbox starting 17 Oct has its
  first full month in November.
- At the end of a full month, over **all series summed**, for each block b (1–7, 8–14, 15–21, 22–end):
  - `A_b` = actual kg;
  - `F_b` = the forecast **without** the month pattern (`shape × level × year_index × market`).
- Observed share: `obs_b = 100 × (A_b/F_b) / Σ(A/F)`, so the four blocks sum to 100.
  - These are shares, so a busy month overall does not distort the pattern. Overall moves belong to the
    level and the year index.
- Per block:
  - `obs_b > pct_b × 1.10` → above; `obs_b < pct_b × 0.90` → below; else normal.
  - 3 consecutive months in the same direction → `pct_b ← mean(obs_b of those 3 months)`, then the four
    blocks are renormalised to sum 100 and that block's streak resets.
- Setup's month pattern is the starting point. The year index is not learned.
- The learned pattern divides actuals and multiplies forecasts from the next day on.
- The founder accepts that the current ~2-month simulation will not trigger this.
- Per-buyer month patterns: an interesting idea for later, **not now**.

### C. One-off orders: never part of the forecast

- The order form gets a **"One-off (not used for the forecast)"** checkbox. The event becomes
  `{"t": "order", …, "oneoff": true}`.
- A one-off order is planned, harvested and served like any other order.
- At day close, a one-off order writes **no** `actual` for that buyer. The day is unknown, not 0, so the
  level neither learns from it nor counts it in the weekly sum.
- A one-off household order is left out of the households `actual` sum.
- A one-off cannot be added on top of a regular order for the same buyer, line and day (the form refuses;
  enter the total). A regular order entered over a one-off replaces it.
- A full month with no orders at all is not judged for the month pattern.
- Old logs are unchanged. Their stored `actual` events replay as before.

### D. Sowing target: expected ("pas")

- `target[d] = B2B expected + households expected`, with no high band.
- Basis label: "Expected orders (no buffer)".
- `protected` (the harvest ceiling's floor: B2B expected + households low) is unchanged.

## Visible in the UI

- **Order form:** the one-off checkbox. The trail shows "one-off" on such an order.
- **Demand tab,** per series: the current week streak, e.g. "2 of 3 weeks above". This explains why the
  level has or hasn't moved.
- **Season card:** the effective month pattern. Learned blocks are marked once they have changed.

## Out of scope

- Per-buyer month patterns.
- Learning the year index.
- Changing the market factor.
- Buyer confirmation as a shortcut.
- A "suspect" notice after 3 days.
- Deploy: the founder tries the sandbox for 1–2 months first. No merge or deploy without asking.

## Verification

- **Unit tests (`test_demand.py`):**
  - 3 high days → level unchanged;
  - 2 above weeks + 1 normal → unchanged;
  - 3 above weeks → level × mean q;
  - 3 below weeks → down by the same rule;
  - the month block moves only after 3 same-direction full months, and the shares stay at 100;
  - a partial month is ignored.
- **Close-day tests:**
  - a one-off order → no actual;
  - a one-off household order is left out of the households sum.
- **Engine test:** the target equals the expected sum.
- **Whole suite, both worlds.** Demo-world tests that depended on fast daily learning get a ruling: the
  new behaviour is intended, and the test is updated with a stated reason.
- **Replay of the founder's log (17 Oct–10 Dec):** a table of the old vs new advice per sowing day, plus
  total seedlings vs the old habit. Expect no jump on 26 Nov.
- **A real `next build`** for the frontend change.
