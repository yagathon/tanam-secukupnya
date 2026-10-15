"""Load the synthetic dataset (data/seed) into Firestore: one doc per row, `_i` keeps file order.

Reference collections are replaced wholesale; visitors' workspaces (users/…) are left alone, unless
--wipe-workspaces (one-off for the daily-engine launch) also deletes the weekly app's leftovers.
Usage: uv run --project backend python scripts/seed_firestore.py [--wipe-workspaces]   (needs ADC on tanam-secukupnya)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from google.cloud import firestore  # noqa: E402

from app.store import COLLECTIONS, FirestoreStore, JsonStore, load_seed  # noqa: E402

BATCH = 400  # Firestore caps a batch at 500 writes

# The weekly app's reference collections and workspace subcollections. Plan 2 removes them once.
OBSOLETE = ("farmers", "partners", "orders")
OLD_WORKSPACE = ("signals", "runs", "notes", "events")


def delete_all(db, refs) -> int:
    refs = list(refs)
    for k in range(0, len(refs), BATCH):
        b = db.batch()
        for r in refs[k:k + BATCH]:
            b.delete(r)
        b.commit()
    return len(refs)


def wipe_old(db) -> None:
    """Drop obsolete reference collections and every visitor workspace (old notes have the weekly
    proposal shape the daily UI cannot render; visitors simply start at day 0 again)."""
    for c in OBSOLETE:
        print(f"{c}: deleted {delete_all(db, (d.reference for d in db.collection(c).stream()))} (obsolete)")
    n = 0
    for user in db.collection("users").list_documents():  # includes uids that only have subcollections
        for c in OLD_WORKSPACE:
            n += delete_all(db, (d.reference for d in user.collection(c).stream()))
    print(f"users/*: deleted {n} workspace docs")


def main(project: str = "tanam-secukupnya", wipe: bool = False) -> None:
    db = firestore.Client(project=project)
    if wipe:
        wipe_old(db)
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
    print("meta/dataset: day0", meta.get("day0"))

    # round-trip check: what the app will load equals the seed files
    FirestoreStore._cache.clear()
    fs, js = FirestoreStore(db), JsonStore()
    for c in COLLECTIONS:
        assert fs.list(c) == js.list(c), c
    assert fs.meta() == js.meta()
    print("round-trip OK")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--wipe-workspaces"]
    main(*args, wipe="--wipe-workspaces" in sys.argv)
