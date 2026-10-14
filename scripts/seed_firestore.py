"""Load the synthetic dataset (data/seed) into Firestore: one doc per row, `_i` keeps file order.

Reference collections are replaced wholesale; visitors' workspaces (users/…) are left alone.
Usage: uv run --project backend python scripts/seed_firestore.py   (needs ADC on tanam-secukupnya)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from google.cloud import firestore  # noqa: E402

from app.store import COLLECTIONS, FirestoreStore, JsonStore, load_seed  # noqa: E402

BATCH = 400  # Firestore caps a batch at 500 writes


def main(project: str = "tanam-secukupnya") -> None:
    db = firestore.Client(project=project)
    ref, meta = load_seed()
    for c in COLLECTIONS:
        old = [d.reference for d in db.collection(c).stream()]
        writes = [("del", r, None) for r in old]
        for i, row in enumerate(ref[c]):
            doc_id = row.get("id") or f"{c[:-1]}_{i:05d}"
            writes.append(("set", db.collection(c).document(doc_id), {**row, "_i": i}))
        for k in range(0, len(writes), BATCH):
            b = db.batch()
            for op, r, data in writes[k:k + BATCH]:
                b.delete(r) if op == "del" else b.set(r, data)
            b.commit()
        print(f"{c}: {len(ref[c])} docs (replaced {len(old)})")
    db.document("meta/dataset").set(meta)
    print("meta/dataset:", meta.get("today"))

    # round-trip check: what the app will load equals the seed files
    FirestoreStore._cache.clear()
    fs, js = FirestoreStore(db), JsonStore()
    for c in COLLECTIONS:
        assert fs.list(c) == js.list(c), c
    assert fs.meta() == js.meta()
    print("round-trip OK")


if __name__ == "__main__":
    main(*sys.argv[1:])
