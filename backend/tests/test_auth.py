import datetime as dt

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from google.auth import crypt, jwt

from app import auth
from app.main import app
from app.store import JsonStore

client = TestClient(app)


@pytest.fixture(scope="module")
def signer():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    pem_key = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    return crypt.RSASigner.from_string(pem_key, key_id="k1"), cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture
def auth_on(monkeypatch, signer):
    monkeypatch.setenv("AUTH", "on")
    monkeypatch.setattr(auth, "_public_certs", lambda: {"k1": signer[1]})


def token(signer, uid="visitor1", aud=auth.PROJECT, iss=None):
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    claims = {"iss": iss or f"https://securetoken.google.com/{auth.PROJECT}", "aud": aud, "sub": uid,
              "iat": now, "exp": now + 600}
    return jwt.encode(signer[0], claims).decode()


def test_health_is_public(auth_on):
    assert client.get("/api/health").status_code == 200


def test_routes_need_a_token(auth_on):
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/state", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_valid_token_is_accepted(auth_on, signer):
    r = client.get("/api/state", headers={"Authorization": f"Bearer {token(signer)}"})
    assert r.status_code == 200 and r.json()["today"] == "2026-10-12"


def test_token_for_another_project_or_issuer_is_rejected(auth_on, signer):
    for t in (token(signer, aud="other-project"), token(signer, iss="https://evil.example")):
        assert client.get("/api/state", headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_workspaces_are_per_user():
    base = JsonStore()
    a, b = base.for_user("a"), base.for_user("b")
    a.put("notes", {"text": "hi"})
    assert len(a.list("notes")) == 1 and b.list("notes") == []
    assert a.list("crops") == b.list("crops")  # reference data is shared
    a.reset()
    assert a.list("notes") == [] and base.for_user("a").list("crops")


def test_reference_data_is_read_only():
    with pytest.raises(ValueError):
        JsonStore().put("crops", {"id": "x"})
