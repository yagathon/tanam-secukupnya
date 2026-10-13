"""Data access behind one small interface.

`JsonStore` reads the seed files and keeps writes in memory (local dev, tests, and the fallback
when Firestore is not configured). The Firestore implementation will satisfy the same `Store`
protocol, so the routes and the service never know which one they talk to.
"""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Protocol

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"
COLLECTIONS = ("crops", "farmers", "partners", "households", "orders", "batches")


class Store(Protocol):
    def list(self, collection: str) -> list[dict]: ...
    def get(self, collection: str, id: str) -> dict | None: ...
    def put(self, collection: str, doc: dict) -> dict: ...
    def meta(self) -> dict: ...
    def reset(self) -> None: ...


class JsonStore:
    def __init__(self, seed_dir: Path = SEED_DIR):
        self.seed_dir = seed_dir
        self.reset()

    def reset(self) -> None:
        self._data: dict[str, list[dict]] = {
            c: json.loads((self.seed_dir / f"{c}.json").read_text()) for c in COLLECTIONS
        }
        self._data.update({"signals": [], "notes": [], "runs": []})
        self._meta = json.loads((self.seed_dir / "planted_patterns.json").read_text())["meta"]

    def list(self, collection: str) -> list[dict]:
        return copy.deepcopy(self._data.get(collection, []))

    def get(self, collection: str, id: str) -> dict | None:
        return next((copy.deepcopy(d) for d in self._data.get(collection, []) if d.get("id") == id), None)

    def put(self, collection: str, doc: dict) -> dict:
        doc = {**doc, "id": doc.get("id") or uuid.uuid4().hex[:12]}
        rows = self._data.setdefault(collection, [])
        rows[:] = [d for d in rows if d.get("id") != doc["id"]] + [doc]
        return copy.deepcopy(doc)

    def meta(self) -> dict:
        return dict(self._meta)
