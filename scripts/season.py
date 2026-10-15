"""Season comparison: 26 weeks × 3 sowing strategies × 5 world seeds → data/seed/season.json.

Cobweb (sow for what sold last week), fixed (the same count every sow day) and tanam (the engine)
each run the same truth world from the same DAY0 farm. The UI's Season tab reads the result; the
sowing series is kept for the main seed only (the chart shows one season).

    uv run --project backend python scripts/season.py      # ~2 min
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import sim  # noqa: E402
from app import world as W
from app.growth import crop_from_dict  # noqa: E402

SEED_DIR = ROOT / "data" / "seed"
SEEDS = (W.SEED, 1, 2, 3, 7)
METRICS = ("waste_pct", "b2b_fill_pct", "hh_fill_pct", "sowing_cv")


def main() -> None:
    crop = crop_from_dict(json.loads((SEED_DIR / "crops.json").read_text())[0])
    runs, sowings = [], {}
    for seed in SEEDS:
        w = W.build(seed)
        start = sim.warmup(crop, w)
        for strategy in sim.STRATEGIES:
            r = sim.season(crop, w, strategy, start=start)
            s = r.pop("sowings")
            if seed == W.SEED:
                sowings[strategy] = s
            runs.append(r)
            print(r, flush=True)
    summary = {s: {m: round(statistics.fmean(r[m] for r in runs if r["strategy"] == s), 1) for m in METRICS}
               for s in sim.STRATEGIES}
    out = {"days": W.FUTURE_DAYS, "seeds": list(SEEDS), "main_seed": W.SEED, "summary": summary,
           "runs": runs, "sowings": sowings, "synthetic": True}
    (SEED_DIR / "season.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
