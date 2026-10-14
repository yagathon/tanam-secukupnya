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
| `just eval [dev\|holdout]` | G1 benchmark (see `eval/README.md`) |
| `just seed-firestore` | load `data/seed` into Firestore |
| `just deploy` | tests → Cloud Build → Cloud Run → UI build → Hosting → smoke test |
