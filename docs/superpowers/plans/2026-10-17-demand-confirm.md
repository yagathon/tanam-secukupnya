# Demand confirm — implementation plan

> Executed inline (superpowers:executing-plans), founder said "ya kerjakan" on 2026-10-17.

**Goal:** the forecast changes only on confirmed evidence: weekly level and monthly pattern, one-off orders
excluded, and sowing targets expected demand.

**Spec:** `docs/superpowers/specs/2026-10-17-demand-confirm-design.md`

## Global constraints

- Week = Mon–Sun. Thresholds ±10%. 3 confirming weeks or months. Up and down are symmetric.
- No merge or deploy. Branch `feat/demand-confirm`.
- Sandbox UI text is English. Currency is not involved.

## Founder's verification ask

Replay with **each sowing = that day's recommendation**, run to **31 Dec**, and show the year-end totals.
Run it for the old engine and the new one, on the same orders.

## Tasks

1. **Weekly level** (`app/demand.py`, `tests/test_demand.py`)
   - Remove the ALPHA and ALPHA_SHIFT level updates.
   - Keep the residuals for σ.
   - At each Sunday, compute q = A/F over the week's known days.
   - Streak per series; after 3 same-direction weeks, level ×= mean q.
   - `Fit.streak = (dir, weeks)`.
   - Tests:
     - 3 high days → level unchanged;
     - 2 above + 1 normal → unchanged;
     - 3 above → level × mean q;
     - 3 below → down.
   - Replace `test_one_low_order_moves_level_a_little_three_a_lot`.
2. **Monthly pattern** (`app/demand.py`)
   - At the end of each fully covered month, when a season is set, compute obs shares from the summed
     series.
   - Per-block streak; after 3 same-direction months, pct ← mean obs, then renormalise to 100.
   - `DemandModel.season` = the effective season.
   - `DemandModel.learned_blocks` = the blocks that moved.
   - Tests:
     - moves only after 3 full months;
     - a partial month is ignored;
     - the shares sum to 100.
3. **One-off orders** (`app/sandbox.py`, `app/state.py`)
   - The order form takes `oneoff`.
   - The event carries `oneoff: true`.
   - State keeps `oneoff_orders`.
   - `close_day`: no b2b actual for a one-off order; the households sum leaves one-off orders out.
   - `describe` adds " · one-off".
   - Tests in `test_sandbox.py`.
4. **Pas target** (`app/engine.py`, `app/farm.py`)
   - `target = b2b_e + hh_e`.
   - Basis label "Expected orders (no buffer)".
   - Engine test.
5. **API + UI**
   - Demand series gain `streak`.
   - The demand/season response gains the effective `month_pct` and `learned_blocks`.
   - The order form gets a one-off checkbox.
   - The Demand tab shows "N of 3 weeks above/below".
   - The Season card marks learned blocks.
   - Run vitest and a real `next build`.
6. **Verification**
   - Full backend suite.
   - Script: rebuild the founder's log keeping setup + orders.
     - Each Mon/Thu, sow exactly the recommendation.
     - Harvests are the engine's planned send.
     - Orders after 10 Dec repeat the same weekday 2 weeks earlier.
     - Run to 31 Dec.
   - Report seedlings, harvested, waste, shortfall (kg to buy at the market), old vs new.
