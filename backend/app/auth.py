"""Firebase anonymous auth: verify the ID token the browser sends, return the visitor's uid.

The uid scopes the visitor's workspace (their notes and signals). Anonymous sign-in is not a
security boundary for the dataset (it is synthetic and public); it keeps visitors' demo state
apart and gives every Gemini call an identity.

`AUTH=off` (local dev, tests) skips the check and uses one local uid.
"""

from __future__ import annotations

import os
import threading
import time

from fastapi import Header, HTTPException

from app.store import LOCAL_UID

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "tanam-secukupnya")
CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
CERTS_TTL = 3600

_certs: dict = {"at": 0.0, "certs": {}}
_lock = threading.Lock()


def _public_certs() -> dict[str, str]:
    with _lock:
        if time.time() - _certs["at"] > CERTS_TTL:
            import requests

            r = requests.get(CERTS_URL, timeout=10)
            r.raise_for_status()
            _certs.update(at=time.time(), certs=r.json())
        return _certs["certs"]


def verify(token: str) -> str:
    """Firebase ID token → uid. Raises ValueError when the token is not valid for this project."""
    from google.auth import jwt

    claims = jwt.decode(token, certs=_public_certs(), audience=PROJECT)
    if claims.get("iss") != f"https://securetoken.google.com/{PROJECT}":
        raise ValueError("wrong issuer")
    uid = claims.get("sub") or ""
    if not uid or len(uid) > 128:
        raise ValueError("no subject")
    return uid


def current_uid(authorization: str | None = Header(default=None)) -> str:
    if os.environ.get("AUTH", "on") == "off":
        return LOCAL_UID
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign-in required (Firebase anonymous auth).")
    try:
        return verify(authorization.removeprefix("Bearer ").strip())
    except Exception as e:
        raise HTTPException(401, f"Invalid sign-in token ({type(e).__name__}).") from e
