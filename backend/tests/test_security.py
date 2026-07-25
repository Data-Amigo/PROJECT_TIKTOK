"""Crypto core — password hashing and JWTs. Pure, no DB, so we test hard cases."""

import jwt
import pytest

from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_plaintext_and_verifies():
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert h.startswith("$argon2")             # Argon2id, not something weaker
    assert verify_password("correct horse battery staple", h) is True
    assert verify_password("wrong password", h) is False


def test_same_password_hashes_differently():
    """Salting: two hashes of the same password must differ (no rainbow tables)."""
    assert hash_password("abc12345") != hash_password("abc12345")


def test_verify_survives_garbage_hash():
    """A corrupt stored hash returns False, never crashes the login path."""
    assert verify_password("anything", "not-a-real-hash") is False


def test_token_roundtrips():
    token = create_access_token("42")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == "access"


def test_expired_token_is_rejected():
    token = create_access_token("1", expires_minutes=-1)  # already expired
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_is_rejected():
    token = create_access_token("1")
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(tampered)
