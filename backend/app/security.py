"""
Security primitives — password hashing and JWT signing. Pure crypto, no DB.

Two jobs, kept together because they're the trust core of the whole app:
  1. Passwords are NEVER stored — only Argon2id hashes. Even we can't read them.
  2. Login issues a signed JWT; every protected request proves it holds one.

Argon2id is the current OWASP-recommended password hash (memory-hard, resists
GPU cracking). We use argon2-cffi's sensible defaults rather than hand-tuning —
the library tracks the recommended parameters so we don't have to.
"""

from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import settings

# One hasher, reused. Holds the (safe, current) cost parameters.
_hasher = PasswordHasher()


# ── Passwords ─────────────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    """Argon2id hash of a plaintext password. The result embeds the salt and
    the cost parameters, so verify() needs nothing else stored."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """True iff `plain` matches `hashed`. Returns False (never raises) on a
    mismatch or a malformed stored hash — callers get a clean boolean, and a
    corrupt hash can't crash a login."""
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False


# ── JWT access tokens ─────────────────────────────────────────────────────────
def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """Sign a token whose `sub` is the account id. Signed with SECRET_KEY, so
    only our server can mint or trust it — the client can read it but not forge
    a different account into it."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload = {"sub": subject, "iat": now, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Verify signature + expiry and return the claims. Raises jwt.PyJWTError
    (its subclasses: ExpiredSignatureError, InvalidTokenError, …) on anything
    wrong — the caller maps that to a 401. We never trust an unverified token."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
