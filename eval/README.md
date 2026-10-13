# G1 benchmark: Bahasa notes → structured signals

G1 reads a WhatsApp-style note (Indonesian, slang, typos, some Sundanese) and proposes either
**demand signals**, a **harvest issue**, or **nothing**. This folder holds the labeled notes and the
results of running Gemini on them.

| File | What |
|---|---|
| `notes_labeled.jsonl` | **Dev set**, 45 notes. The prompt was tuned while looking at these results. |
| `notes_holdout.jsonl` | **Held-out set**, 15 notes, written *after* prompt tuning and never used to change it. Report this number. |
| `results/g1-<set>-<model>.md` | Score table + every miss |
| `results/g1-<set>-<model>.jsonl` | Every reading, for inspection |

Run: `just eval` (dev) · `just eval holdout` · `just eval holdout gemini-3-flash-preview`.
Needs Application Default Credentials on the `tanam-secukupnya` project.

## Label format (one JSON object per line)

```json
{"id": "n01", "received_on": "2026-10-12", "sender": "operator",
 "text": "bu, resto A minggu depan pakcoy kurangin dulu ya separo, lg renovasi dapur",
 "expected": {"kind": "signals", "signals": [
   {"scope": "partner:resto_a", "crop": "pakcoy", "effect_pct": -50,
    "week_from": "2026-10-19", "week_to": "2026-10-19", "cause_category": "renovation"}]},
 "label_note": "optional: why the label is what it is"}
```

- `sender`: a partner id, a farmer id, or `operator`. The model sees only `text`, `sender` and the
  context (aliases, average kg per week, the table of coming Mondays), never `label_note`.
- Weeks are keyed by their **Monday**. `week_to` is inclusive. `null` means open-ended ("mulai minggu depan").
- `crop: null` = every crop the scope buys.
- Harvest issue: `{farmer_id, crop, loss_pct, delay_days, harvest_week|null, cause_category}`.
- Cause categories live in `backend/app/notes.py` (`DEMAND_CAUSES`, `HARVEST_CAUSES`).
- `backend/tests/test_notes.py` checks that every label uses valid ids, Monday dates and known
  categories, and that a perfect reading scores 100%.

## Scoring

Each note is scored on its **kind**, then field by field:

| Kind | Fields | Correct when |
|---|---|---|
| signals | scope, crop, direction, magnitude, period, cause | magnitude = same bucket (stop / ±small <15% / ±medium 15–40% / ±large >40%); period = exact Monday range |
| harvest issue | farmer, crop, magnitude, delay, period, cause | magnitude within ±10 points; delay exact |
| none | — | anything proposed counts as a false alarm |

Predicted signals are paired with labeled ones by best field agreement. A `crop: null` signal is
expanded into one per crop the scope buys, so "pakcoy and sawi +30%" is accepted either as one signal
or as two. Predicted signals with no labeled counterpart count as **extra**, meaning a proposal the
operator would have to reject.

## Honest caveats

- All notes are **synthetic** and written by the same person (Claude) who wrote the prompt and the
  labels. The founder reviews them for realism (checklist item). A real benchmark needs notes from
  real partners and farmers.
- Some notes are truly ambiguous (`label_note` says so, e.g. n19 "2 minggu ke depan" sent on a Monday).
  In the product the operator settles these when accepting.
- The model only *proposes*. Nothing reaches the forecast until a person accepts it, and the server
  drops any id, crop or date outside what the context allows (`notes.sanitize`).
