# Tanam Secukupnya — *plant just enough*

AI-assisted sowing planner that breaks the farm oversupply "doom cycle" (the cobweb cycle):
it reads demand signals from an aggregator's buyer network, forecasts demand with an honest
uncertainty band, and turns it into grade-aware, pest-buffered sowing recommendations with
layered offtake assurance for small farmers.

Built for the **Google Cloud AI Builder Cup 2026** — theme: *Sustainability & Social Impact*.

> Status: work in progress (build window 13–18 Oct 2026).

## Stack
Gemini on Vertex AI · Cloud Run (FastAPI) · Firestore · Firebase Hosting + Auth (Next.js)

## Data
All data in this repository is **synthetic**, generated from real field experience at a small
Indonesian farm-to-buyer aggregator. No real people or businesses appear in it.

## How it runs on Google Cloud

```
browser ──► Firebase Hosting (static Next.js UI)
   │  Firebase anonymous sign-in → ID token on every API call
   └─ /api/** rewrite ──► Cloud Run `tanam-api` (FastAPI, asia-southeast2)
                            ├─ verifies the token → visitor uid
                            ├─ Firestore: reference data (seeded) + users/{uid}/{notes,signals}
                            └─ Gemini on Vertex AI (global endpoint)
```

- **Firestore** holds the synthetic dataset (crops, farmers, partners, households, orders,
  batches, `meta/dataset`), loaded with `just seed-firestore`, and each visitor's workspace under
  `users/{uid}/…`. The API loads the reference data once per instance; workspace reads and writes
  go straight to Firestore, so a visitor's notes survive reloads and instance restarts.
- **Firebase Auth (anonymous)** gives every visitor a uid without a sign-up form. It keeps
  visitors' demo work apart (nobody sees or overwrites anyone else's notes) and gives every Gemini
  call an identity. Gemini calls are also cached by input and capped per day.
- Locally, `just api` runs the same API on the seed JSON files with auth off; no GCP needed.

| Command | What |
|---|---|
| `just test` | backend tests |
| `just api` | API on :8100 (JSON store, auth off); `cd frontend && npx next dev -p 3100` for the UI |
| `just eval [dev\|holdout\|sandbox]` | G1 benchmark (see `eval/README.md`) |
| `just seed-firestore` | load `data/seed` into Firestore |
| `just deploy` | tests → Cloud Build → Cloud Run → UI build → Hosting → smoke test |

## Sandbox (`/sandbox`)

A blank farm on the same engine: you set the crop and the buyers, then enter each day yourself
and watch the decisions move. Nothing is hidden: you are the world. **Clear** wipes the logged days
and keeps the setup. The **Trail** tab shows each day's numbers, with what changed highlighted.

To skip the typing, load a prefilled farm: download
[`sandbox-logs/example-farm-2026-10-18_to_2026-11-25.json`](sandbox-logs/example-farm-2026-10-18_to_2026-11-25.json)
(a baby-pakcoy farm with a restaurant and retail buyers, 18 Oct – 25 Nov) and press **Load my log**
in the sandbox's Setup tab.

Setup tables accept a paste from Google Sheets (tab-separated) or CSV (`,` or `;`). A header
row is optional, and `12,5` and `12.5` both read as 12.5:

| Table | Columns |
|---|---|
| Growth curve | `day` · `grams` (both increasing) |
| Buyers | `name` · `type` (business/household) · `line` · `usual kg/week` · `weekdays` (e.g. `Tue Fri`; empty = every day) · `min kg` |
| Beds | `line` · `sown on` (YYYY-MM-DD) · `seedlings` |

Daily input is either a form or a free-text note: Gemini reads the note into a fixed-format card
(`ORDER · Restaurant A · regular · 16.0 kg · Tue 20 Oct`, `HARVEST · Bed 1 · 10.5 kg · sample 640 g / 330 g`,
`LOSS · Bed 2 · 25% · caterpillars`), and nothing is logged until you press **OK**. **Edit** opens
the matching form, prefilled.

**Model B growth.** A bed's curve is the reference curve scaled by a percentage: a stunted bed
(often from planting too densely) stays small instead of running late. Each 5-biggest/5-smallest
sample updates that bed's percentage. Healthy sampled beds also move the reference curve slowly,
one age node at a time. This is a calibration loop, not reinforcement learning (RL in simulation
is on the roadmap).

