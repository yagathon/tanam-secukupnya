"""G1 benchmark: run every labeled note through Gemini, score field by field, write a report.

    just eval                         # dev set, default model
    just eval holdout                 # held-out set (never used to tune the prompt)
    just eval dev gemini-3-flash-preview

Writes eval/results/g1-<set>-<model>.jsonl (every reading) and .md (the table).
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
SET = sys.argv[1] if len(sys.argv) > 1 else "dev"
if len(sys.argv) > 2:
    os.environ["GEMINI_MODEL"] = sys.argv[2]

from app import gemini, notes, service  # noqa: E402
from app.store import JsonStore  # noqa: E402

LABELS = ROOT / "eval" / {"dev": "notes_labeled.jsonl", "holdout": "notes_holdout.jsonl"}[SET]
OUT = ROOT / "eval" / "results"


def main() -> None:
    store = JsonStore()
    rows = [json.loads(line) for line in LABELS.read_text().splitlines() if line.strip()]
    state = {"today": rows[0]["received_on"], **{c: store.list(c) for c in ("crops", "farmers", "partners", "households")}}
    ctx = notes.context(state, service.recent_avg_kg(store))
    sc = notes.scope_crops(state)

    def run(r: dict) -> dict:
        t0 = time.monotonic()
        try:
            out = gemini.read_note(r["text"], r["sender"], r["received_on"], ctx)
            got, dropped = notes.sanitize(out["reading"], state)
            return {**r, "got": got, "dropped": dropped, "tokens": out["tokens"], "model": out["model"],
                    "secs": round(time.monotonic() - t0, 2), "score": notes.score(r["expected"], got, sc)}
        except Exception as e:  # a failed call scores as a wrong "none"
            got = {"kind": "error", "signals": [], "harvest_issue": None}
            return {**r, "got": got, "error": repr(e)[:300], "secs": round(time.monotonic() - t0, 2),
                    "score": notes.score(r["expected"], got, sc)}

    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(run, rows))

    model = gemini.MODEL
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / f"g1-{SET}-{model}.jsonl").open("w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    report = render(results, model)
    (OUT / f"g1-{SET}-{model}.md").write_text(report)
    print(report)


def render(results: list[dict], model: str) -> str:
    kind_ok = sum(r["score"]["kind_ok"] for r in results)
    per_field: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        for k, v in r["score"]["fields"].items():
            name = k.split(".")[-1]
            per_field[f"{r['expected']['kind']}/{name}"][v] += 1
    all_fields = [v for r in results for v in r["score"]["fields"].values()]
    false_alarms = sum(1 for r in results if r["expected"]["kind"] == "none" and r["got"]["kind"] != "none")
    extras = sum(r["score"]["extra"] for r in results if r["expected"]["kind"] != "none")
    tok_in = [r["tokens"]["in"] for r in results if r.get("tokens") and r["tokens"]["in"]]
    tok_out = [r["tokens"]["out"] for r in results if r.get("tokens") and r["tokens"]["out"]]
    secs = sorted(r["secs"] for r in results)
    pct = lambda a, b: f"{100 * a / b:.0f}%" if b else "—"  # noqa: E731

    lines = [f"# G1 benchmark — {SET} set — {model}", "",
             f"{len(results)} labeled notes (synthetic, Bahasa/Sundanese WhatsApp style), received {results[0]['received_on']}.", "",
             "| Measure | Result |", "|---|---|",
             f"| Kind correct (signals / harvest issue / none) | {kind_ok}/{len(results)} ({pct(kind_ok, len(results))}) |",
             f"| Field-level accuracy (all scored fields) | {sum(all_fields)}/{len(all_fields)} ({pct(sum(all_fields), len(all_fields))}) |",
             f"| False alarms on noise notes | {false_alarms}/{sum(r['expected']['kind'] == 'none' for r in results)} |",
             f"| Extra signals not in the label | {extras} |",
             f"| Errors | {sum('error' in r for r in results)} |",
             f"| Median latency | {secs[len(secs) // 2]:.1f} s |",
             f"| Avg tokens in / out | {sum(tok_in) // max(1, len(tok_in))} / {sum(tok_out) // max(1, len(tok_out))} |",
             "", "| Field | Correct |", "|---|---|"]
    for k in sorted(per_field):
        c = per_field[k]
        lines.append(f"| {k} | {c[True]}/{c[True] + c[False]} ({pct(c[True], c[True] + c[False])}) |")
    misses = [r for r in results if not r["score"]["kind_ok"] or not all(r["score"]["fields"].values()) or r["score"]["extra"]]
    lines += ["", f"## Misses ({len(misses)})", ""]
    for r in misses:
        wrong = [k for k, v in r["score"]["fields"].items() if not v]
        lines.append(f"- **{r['id']}** `{r['text']}` — expected {r['expected']['kind']}, got {r['got']['kind']}"
                     + (f"; wrong: {', '.join(wrong)}" if wrong else "") + (f"; extra {r['score']['extra']}" if r['score']['extra'] else "")
                     + (f"; error {r['error']}" if "error" in r else ""))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
