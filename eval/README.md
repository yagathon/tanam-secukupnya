# G1 benchmark: Bahasa notes → one proposed farm event

G1 reads a WhatsApp-style note (Indonesian, slang, typos, some Sundanese) and proposes one of six
kinds: **orders**, **harvest** (with the optional 5-biggest/5-smallest size sample), **sowing**
(or a postponed sowing), **loss**, a demand **signal**, or **none**. A person accepts or rejects
every proposal; nothing reaches the farm until accepted.

| File | What |
|---|---|
| `notes_labeled.jsonl` | **Dev set**, 60 notes. The prompt was tuned while looking at these results. |
| `notes_holdout.jsonl` | **Held-out set**, 18 notes, written *after* prompt tuning and never used to change it. Report this number. |
| `results/g1-<set>-<model>.md` | Score table + every miss |
| `results/g1-<set>-<model>.jsonl` | Every reading, for inspection |

Run: `just eval` (dev) · `just eval holdout` · `just eval holdout gemini-3-flash-preview`.
Needs Application Default Credentials on the `tanam-secukupnya` project.

Every note is read against the DAY0 farm (2026-10-12): the same context a visitor's first note
gets (buyer aliases, bed labels in the ground, usual kg per order, a 35-day date table).

## Label format

```json
{"id": "d02", "received_on": "2026-10-12", "sender": "farmer",
 "text": "panen bed 41 td pagi 11,5 kg. timbang 5 gede 620gr 5 kecil 310",
 "expected": {"kind": "harvest", "harvest": {"bed": "Bed 41", "kg": 11.5, "big5_g": 620, "small5_g": 310}}}
```

`expected` uses the sanitized proposal's shape:
- `orders: [{buyer, line, kg, day}]`
- `harvest: {bed, kg, big5_g, small5_g}`
- `sowing: {line, postponed, seedlings}`
- `loss: {bed, pct, cause_category}`
- `signals: [{scope, line, effect_pct, date_from, date_to, cause_category}]`

`backend/tests/test_labels.py` checks that a perfect reading of every label survives the
sanitizer and scores 100%.

## Scoring

Each note is scored on its **kind**, then field by field (`backend/app/notes.py: score`):

| Kind | Fields (tolerance) |
|---|---|
| orders | buyer, line, kg (±5% or 0.1 kg), day |
| harvest | bed, kg (±5% or 0.1 kg), sample (both figures ±2% or 5 g) |
| sowing | line, postponed, seedlings (exact) |
| loss | bed, pct (±10 points), cause category |
| signal | scope, line, direction, magnitude bucket, period, cause category |

List kinds are matched item to item; unmatched proposed items count as **extra** (false alarms a
person would have to reject). A failed call scores every field wrong.
