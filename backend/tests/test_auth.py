"""Auth endpoints — signup, login, /me. The full security surface, end to end."""

import random

from sqlalchemy import select

from app.models.account import Account
from app.security import create_access_token

# Randomized per run so these tests never collide with a REAL committed account
# (email/phone are DB-unique; a fixed test phone once clashed with live data).
# Tests roll back, so this base stays constant within a run — dup-detection
# tests still work.
_SUFFIX = random.randint(10_000_000, 99_999_999)
BASE = {
    "name": "Mama Wanjiku",
    "email": f"mama_{_SUFFIX}@example.com",
    "phone": f"07{_SUFFIX}",  # → 254 7 XXXXXXXX after normalization
    "password": "supersecret",
}
_EMAIL = BASE["email"]
_PHONE = f"2547{_SUFFIX}"  # what "07{suffix}" normalizes to


def _signup(client, **overrides):
    return client.post("/api/auth/signup", json={**BASE, **overrides})


# ── Signup ────────────────────────────────────────────────────────────────────
def test_signup_creates_account_hashes_password_normalizes_phone(client, db_session):
    r = _signup(client)
    assert r.status_code == 201
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]

    acct = db_session.scalar(select(Account).where(Account.email == _EMAIL))
    assert acct is not None
    assert acct.phone == _PHONE                 # normalized at the border
    assert acct.password_hash != "supersecret"          # never stored in the clear
    assert acct.password_hash.startswith("$argon2")     # Argon2id


def test_signup_duplicate_email_conflicts(client):
    _signup(client)
    r = _signup(client, phone="0712345679")             # new phone, same email
    assert r.status_code == 409


def test_signup_duplicate_phone_conflicts(client):
    _signup(client)
    r = _signup(client, email="someone.else@example.com")
    assert r.status_code == 409


def test_signup_rejects_bad_email(client):
    assert _signup(client, email="not-an-email").status_code == 422


def test_signup_rejects_bad_phone(client):
    assert _signup(client, phone="12345").status_code == 422


def test_signup_rejects_short_password(client):
    assert _signup(client, password="short").status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────
def test_login_succeeds_with_correct_credentials(client):
    _signup(client)
    r = client.post("/api/auth/login", json={"email": _EMAIL, "password": "supersecret"})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_wrong_password_is_401(client):
    _signup(client)
    r = client.post("/api/auth/login", json={"email": _EMAIL, "password": "WRONGPASS"})
    assert r.status_code == 401


def test_login_unknown_email_is_401_same_as_wrong_password(client):
    # No account exists → still 401 with the SAME message (no enumeration).
    r = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "whatever12"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password."


# ── /me (the protected route) ─────────────────────────────────────────────────
def test_me_requires_a_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_a_bad_token(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert r.status_code == 401


def test_me_returns_the_account_without_the_hash(client):
    token = _signup(client).json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == _EMAIL
    assert body["phone"] == _PHONE
    assert "password_hash" not in body   # the response schema can't leak it


def test_me_rejects_an_expired_token(client, db_session):
    _signup(client)
    acct = db_session.scalar(select(Account))
    expired = create_access_token(str(acct.id), expires_minutes=-1)
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
