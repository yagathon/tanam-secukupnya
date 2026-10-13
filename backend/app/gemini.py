"""Gemini on Vertex AI. One lazily built client; the prompts (G1–G5) land here as they are written.

Vertex serves the Flash models from the `global` endpoint only (the Jakarta region rejects them),
so the model location is separate from where Cloud Run and Firestore live.
"""

from __future__ import annotations

import os
from functools import lru_cache

from google import genai

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "tanam-secukupnya")
LOCATION = os.environ.get("GEMINI_LOCATION", "global")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


@lru_cache(maxsize=1)
def client() -> genai.Client:
    return genai.Client(vertexai=True, project=PROJECT, location=LOCATION)


def ping() -> dict:
    """Fixed prompt, so the public route cannot be used to spend tokens on arbitrary input."""
    r = client().models.generate_content(model=MODEL, contents="Reply with exactly one word: halo")
    return {"model": r.model_version or MODEL, "reply": (r.text or "").strip()}
