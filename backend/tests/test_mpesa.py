"""M-Pesa (Daraja) client — the parts that must hold regardless of Safaricom.
No real network: pure helpers, the config guard, and a monkeypatched happy path."""

import base64

import pytest

from app import config
from app.services import mpesa


def _configure(monkeypatch, **over):
    """Set sandbox-ish M-Pesa settings for a test."""
    defaults = {
        "mpesa_consumer_key": "ck",
        "mpesa_consumer_secret": "cs",
        "mpesa_shortcode": "174379",
        "mpesa_passkey": "testpass",
        "mpesa_callback_url": "https://example.com/cb",
    }
    for k, v in {**defaults, **over}.items():
        monkeypatch.setattr(config.settings, k, v)


def test_password_is_base64_of_shortcode_passkey_timestamp():
    pw = mpesa._password("174379", "testpass", "20260101120000")
    # Independent check: decodes back to the exact concatenation, in order.
    assert base64.b64decode(pw).decode() == "174379testpass20260101120000"


def test_timestamp_is_14_digits():
    ts = mpesa._timestamp()
    assert len(ts) == 14 and ts.isdigit()


def test_build_stk_payload_is_correct_and_capped(monkeypatch):
    _configure(monkeypatch)
    p = mpesa.build_stk_payload(
        "254712345678", 600, "ORDER-123456789", "Ripped Jeans purchase", timestamp="20260101120000"
    )
    assert p["BusinessShortCode"] == "174379"
    assert base64.b64decode(p["Password"]).decode() == "174379testpass20260101120000"
    assert p["Amount"] == 600 and isinstance(p["Amount"], int)
    assert p["PartyA"] == "254712345678" and p["PhoneNumber"] == "254712345678"
    assert p["CallBackURL"] == "https://example.com/cb"
    assert len(p["AccountReference"]) <= 12          # Daraja's hard cap
    assert len(p["TransactionDesc"]) <= 13


def test_missing_credentials_raise_listing_what_is_missing(monkeypatch):
    _configure(monkeypatch, mpesa_consumer_key="", mpesa_passkey="")
    with pytest.raises(mpesa.MpesaError, match="MPESA_CONSUMER_KEY.*MPESA_PASSKEY|MPESA_PASSKEY"):
        mpesa._require_credentials()


def test_stk_push_needs_a_callback_url(monkeypatch):
    _configure(monkeypatch, mpesa_callback_url="")
    with pytest.raises(mpesa.MpesaError, match="MPESA_CALLBACK_URL"):
        mpesa.stk_push("0712345678", 600, "ref", "desc")


def test_stk_push_rejects_a_bad_phone(monkeypatch):
    _configure(monkeypatch)
    with pytest.raises(mpesa.MpesaError, match="valid Kenyan phone"):
        mpesa.stk_push("12345", 600, "ref", "desc")  # digits, but not a KE mobile


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_stk_push_happy_path(monkeypatch):
    _configure(monkeypatch)
    # Skip OAuth network by seeding a live token in the cache.
    monkeypatch.setitem(mpesa._token_cache, "value", "tok")
    from datetime import datetime, timedelta

    monkeypatch.setitem(mpesa._token_cache, "expires_at", datetime.now() + timedelta(hours=1))

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["auth"] = headers["Authorization"]
        captured["amount"] = json["Amount"]
        return _FakeResp({
            "ResponseCode": "0",
            "CheckoutRequestID": "ws_CO_123",
            "MerchantRequestID": "merch_1",
            "CustomerMessage": "Success. Request accepted for processing",
        })

    monkeypatch.setattr(mpesa.httpx, "post", fake_post)
    out = mpesa.stk_push("0712345678", 600, "ORDER1", "Jeans")
    assert out["checkout_request_id"] == "ws_CO_123"
    assert captured["auth"] == "Bearer tok"
    assert captured["amount"] == 600
    assert captured["url"].endswith("/mpesa/stkpush/v1/processrequest")


def test_stk_push_surfaces_a_rejection(monkeypatch):
    _configure(monkeypatch)
    from datetime import datetime, timedelta

    monkeypatch.setitem(mpesa._token_cache, "value", "tok")
    monkeypatch.setitem(mpesa._token_cache, "expires_at", datetime.now() + timedelta(hours=1))
    monkeypatch.setattr(
        mpesa.httpx, "post",
        lambda *a, **k: _FakeResp({"ResponseCode": "1", "ResponseDescription": "Invalid shortcode"}),
    )
    with pytest.raises(mpesa.MpesaError, match="Invalid shortcode"):
        mpesa.stk_push("0712345678", 600, "ref", "desc")
