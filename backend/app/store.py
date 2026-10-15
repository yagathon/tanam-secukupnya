"""Data access behind one small interface.

Two kinds of data:
- **reference** (crops, buyers, households, batches, history, meta): the synthetic farm on DAY0.
  Read-only to the app, shared by every visitor.
- **workspace** (notes, events): what a visitor does in the demo. Scoped per user
  (`for_user(uid)`, uid = Firebase anonymous auth). `events` is the visitor's ordered log
  (`{seq, kind: day|note, events}`); their farm state is the reference data with the log replayed.

`JsonStore` reads the seed files and keeps workspaces in memory (local dev, tests).
`FirestoreStore` loads the reference collections from Firestore once per process and reads and
writes workspaces under `users/{uid}/…`. `make_store()` picks one from env `STORE`.
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Protocol

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"
COLLECTIONS = ("crops", "buyers", "households", "batches", "history")
WORKSPACE = ("notes", "events")
LOCAL_UID = "local"
_add_lock = threading.Lock()


class Store(Protocol):
    def list(self, collection: str) -> list[dict]: ...
    def get(self, collection: str, id: str) -> dict | None: ...
    def put(self, collection: str, doc: dict) -> dict: ...
    def add(self, collection: str, doc: dict) -> bool: ...
    def meta(self) -> dict: ...
    def reset(self) -> None: ...
    def for_user(self, uid: str) -> "Store": ...


def load_seed(seed_dir: Path = SEED_DIR) -> tuple[dict[str, list[dict]], dict]:
    data = {c: json.loads((seed_dir / f"{c}.json").read_text()) for c in COLLECTIONS}
    meta = json.loads((seed_dir / "meta.json").read_text())
    return data, meta


def _new_id(doc: dict) -> dict:
    return {**doc, "id": doc.get("id") or uuid.uuid4().hex[:12]}


class JsonStore:
    def __init__(self, seed_dir: Path = SEED_DIR, uid: str = LOCAL_UID, _shared: tuple | None = None):
        if _shared is None:
            ref, meta = load_seed(seed_dir)
            _shared = (ref, meta, {})
        self._ref, self._meta, self._spaces = _shared
        self.uid = uid

    def for_user(self, uid: str) -> "JsonStore":
        return JsonStore(uid=uid, _shared=(self._ref, self._meta, self._spaces))

    def _rows(self, collection: str) -> list[dict]:
        if collection in WORKSPACE:
            return self._spaces.setdefault(self.uid, {}).setdefault(collection, [])
        return self._ref.get(collection, [])

    def reset(self) -> None:
        self._spaces.pop(self.uid, None)

    def list(self, collection: str) -> list[dict]:
        return copy.deepcopy(self._rows(collection))

    def get(self, collection: str, id: str) -> dict | None:
        return next((copy.deepcopy(d) for d in self._rows(collection) if d.get("id") == id), None)

    def put(self, collection: str, doc: dict) -> dict:
        if collection not in WORKSPACE:
            raise ValueError(f"{collection} is reference data (read-only)")
        doc = _new_id(doc)
        rows = self._rows(collection)
        rows[:] = [d for d in rows if d.get("id") != doc["id"]] + [doc]
        return copy.deepcopy(doc)

    def add(self, collection: str, doc: dict) -> bool:
        """Store `doc` under its own id only if no doc has that id yet; False if one already does."""
        with _add_lock:
            if self.get(collection, doc["id"]) is not None:
                return False
            self.put(collection, doc)
            return True

    def meta(self) -> dict:
        return dict(self._meta)


class FirestoreStore:
    """Reference data: top-level collections (seeded by scripts/seed_firestore.py), each doc carrying
    `_i` (its position in the seed file, so list order matches JsonStore). Meta: doc `meta/dataset`.
    Workspace: `users/{uid}/{notes|events}`, ordered by `created_at`."""

    _cache: dict[str, tuple[dict[str, list[dict]], dict]] = {}
    _lock = threading.Lock()

    def __init__(self, client=None, uid: str = LOCAL_UID):
        if client is None:
            from google.cloud import firestore

            client = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT", "tanam-secukupnya"))
        self._db = client
        self.uid = uid
        self._ref, self._meta = self._load_reference()

    def _load_reference(self) -> tuple[dict[str, list[dict]], dict]:
        key = self._db.project
        with self._lock:
            if key not in self._cache:
                ref = {}
                for c in COLLECTIONS:
                    rows = sorted((d.to_dict() for d in self._db.collection(c).stream()), key=lambda r: r["_i"])
                    ref[c] = [{k: v for k, v in r.items() if k != "_i"} for r in rows]
                meta = self._db.document("meta/dataset").get().to_dict()
                if not meta or not ref["crops"]:
                    raise RuntimeError("Firestore is not seeded: run scripts/seed_firestore.py")
                self._cache[key] = (ref, meta)
            return self._cache[key]

    def for_user(self, uid: str) -> "FirestoreStore":
        view = object.__new__(FirestoreStore)
        view._db, view.uid, view._ref, view._meta = self._db, uid, self._ref, self._meta
        return view

    def _col(self, collection: str):
        return self._db.collection("users").document(self.uid).collection(collection)

    def list(self, collection: str) -> list[dict]:
        if collection not in WORKSPACE:
            return copy.deepcopy(self._ref.get(collection, []))
        return sorted((d.to_dict() for d in self._col(collection).stream()), key=lambda r: r.get("created_at", 0))

    def get(self, collection: str, id: str) -> dict | None:
        if collection not in WORKSPACE:
            return next((copy.deepcopy(d) for d in self._ref.get(collection, []) if d.get("id") == id), None)
        snap = self._col(collection).document(id).get()
        return snap.to_dict() if snap.exists else None

    def put(self, collection: str, doc: dict) -> dict:
        if collection not in WORKSPACE:
            raise ValueError(f"{collection} is reference data (read-only)")
        doc = _new_id(doc)
        doc.setdefault("created_at", time.time())
        self._col(collection).document(doc["id"]).set(doc)
        return doc

    def add(self, collection: str, doc: dict) -> bool:
        """Create `doc` under its own id only if no doc has that id yet; False if one already does."""
        from google.api_core.exceptions import AlreadyExists

        if collection not in WORKSPACE:
            raise ValueError(f"{collection} is reference data (read-only)")
        try:
            self._col(collection).document(doc["id"]).create({**doc, "created_at": time.time()})
        except AlreadyExists:
            return False
        return True

    def meta(self) -> dict:
        return dict(self._meta)

    def reset(self) -> None:
        for c in WORKSPACE:
            refs = [d.reference for d in self._col(c).stream()]
            for i in range(0, len(refs), 400):
                batch = self._db.batch()
                for r in refs[i:i + 400]:
                    batch.delete(r)
                batch.commit()


def make_store() -> Store:
    return FirestoreStore() if os.environ.get("STORE") == "firestore" else JsonStore()
