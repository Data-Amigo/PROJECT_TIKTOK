"""
M-Pesa (Daraja) client — SokoLink's payment rail. (M4, step 1)

    consumer key/secret ──> OAuth token ──> STK Push ──> phone prompt
                            (cached)         (Lipa Na M-Pesa Online)   "enter PIN"

This is the ADAPTER for Safaricom's Daraja API. Callers see `stk_push()` and
`access_token()`; they never see base URLs, base64 passwords, or token caching.
Swapping sandbox↔production is one .env value (`MPESA_ENV`); swapping Daraja for
another PSP later is a rewrite of THIS file only.

Two rails-first principles this file exists to serve:
  1. STK Push only ASKS for money — it returns a CheckoutRequestID, NOT a
     payment. Whether the money actually moved is told to us later by
     Safaricom's callback (M4.3). "Callback = truth"; this client never assumes
     success from a 200 here.
  2. Every value that must match between the password and the request (shortcode,
     timestamp) is computed in ONE place (`build_stk_payload`) so they can't
     drift — the #1 cause of Daraja's opaque "invalid" errors.
"""

import base64
from datetime import datetime, timedelta

import httpx

from app.config import settings
from app.utils import normalize_kenyan_phone

_TIMEOUT_S = 30

# Sandbox 174379 is a Paybill shortcode → PayBill transaction type. (A Till/Buy-
# Goods shortcode would use "CustomerBuyGoodsOnline"; revisit at go-live.)
_TRANSACTION_TYPE = "CustomerPayBillOnline"

# OAuth tokens last ~3600s; cache so we don't fetch one per request. Module-level
# is fine for a single-process POC (swap to Redis when we scale out).
_token_cache: dict = {"value": None, "expires_at": datetime.min}


class MpesaError(Exception):
    """Any Daraja failure, with a message safe for a log and a human."""


# ── Pure helpers (no network — the easy part to unit-test) ────────────────────
def _timestamp(now: datetime | None = None) -> str:
    """Daraja's `YYYYMMDDHHMMSS`. The SAME value goes into the password and the
    request body — that's why it's generated once and passed around."""
    return (now or datetime.now()).strftime("%Y%m%d%H%M%S")


def _password(shortcode: str, passkey: str, timestamp: str) -> str:
    """Lipa Na M-Pesa Online password = base64(shortcode + passkey + timestamp).
    Exactly this concatenation, in this order — Daraja re-derives and compares it."""
    return base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()


def build_stk_payload(
    msisdn: str,
    amount: int,
    account_reference: str,
    description: str,
    *,
    timestamp: str | None = None,
) -> dict:
    """Build the exact STK Push request body. Pure (reads config, no network) so
    a test can assert the password/shortcode/phone/amount are right without
    spending a call. `msisdn` must already be canonical 2547…; `amount` whole KES."""
    ts = timestamp or _timestamp()
    return {
        "BusinessShortCode": settings.mpesa_shortcode,
        "Password": _password(settings.mpesa_shortcode, settings.mpesa_passkey, ts),
        "Timestamp": ts,
        "TransactionType": _TRANSACTION_TYPE,
        "Amount": int(amount),
        "PartyA": msisdn,                       # who pays
        "PartyB": settings.mpesa_shortcode,     # who's paid (us)
        "PhoneNumber": msisdn,                  # who gets the prompt
        "CallBackURL": settings.resolved_mpesa_callback_url,
        "AccountReference": account_reference[:12],  # Daraja caps this at 12 chars
        "TransactionDesc": description[:13] or "Payment",  # and this at 13
    }


def _require_credentials() -> None:
    """Fail early, clearly, listing exactly what's missing from .env."""
    missing = [
        name
        for name, val in {
            "MPESA_CONSUMER_KEY": settings.mpesa_consumer_key,
            "MPESA_CONSUMER_SECRET": settings.mpesa_consumer_secret,
            "MPESA_SHORTCODE": settings.mpesa_shortcode,
            "MPESA_PASSKEY": settings.mpesa_passkey,
        }.items()
        if not val
    ]
    if missing:
        raise MpesaError(f"M-Pesa not configured — missing in .env: {', '.join(missing)}.")


# ── Network ───────────────────────────────────────────────────────────────────
def access_token(*, force: bool = False) -> str:
    """A Daraja OAuth bearer token, cached until ~1 min before it expires.

    Auth is HTTP Basic with the consumer key as user and secret as password;
    Daraja returns {access_token, expires_in}."""
    _require_credentials()
    now = datetime.now()
    if not force and _token_cache["value"] and _token_cache["expires_at"] > now:
        return _token_cache["value"]

    try:
        resp = httpx.get(
            f"{settings.mpesa_base_url}/oauth/v1/generate",
            params={"grant_type": "client_credentials"},
            auth=(settings.mpesa_consumer_key, settings.mpesa_consumer_secret),
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        # 400 here almost always = wrong consumer key/secret (or sandbox vs prod).
        raise MpesaError(
            f"M-Pesa auth failed (HTTP {e.response.status_code}). Check the "
            "consumer key/secret and that MPESA_ENV matches the app."
        ) from e
    except httpx.RequestError as e:
        raise MpesaError(f"Could not reach M-Pesa (auth): {e}") from e

    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise MpesaError("M-Pesa auth returned no access_token.")
    expires_in = int(data.get("expires_in", 3600))
    _token_cache["value"] = token
    _token_cache["expires_at"] = now + timedelta(seconds=max(expires_in - 60, 60))
    return token


def stk_push(phone: str, amount: int, account_reference: str, description: str) -> dict:
    """Trigger a Lipa Na M-Pesa Online prompt on the customer's phone.

    Returns Daraja's acknowledgement {checkout_request_id, merchant_request_id,
    customer_message} — proof the PROMPT was sent, NOT that payment happened.
    The paid/failed truth arrives at the callback (M4.3). Raises MpesaError with
    a human message on any failure."""
    _require_credentials()
    if not settings.resolved_mpesa_callback_url:
        raise MpesaError(
            "No M-Pesa callback URL — set MPESA_CALLBACK_URL, or deploy on Railway "
            "(RAILWAY_PUBLIC_DOMAIN) / use a tunnel in local dev."
        )
    try:
        msisdn = normalize_kenyan_phone(phone)
    except ValueError as e:
        raise MpesaError(str(e)) from e
    if int(amount) < 1:
        raise MpesaError("Amount must be at least KES 1.")

    payload = build_stk_payload(msisdn, amount, account_reference, description)
    try:
        resp = httpx.post(
            f"{settings.mpesa_base_url}/mpesa/stkpush/v1/processrequest",
            headers={"Authorization": f"Bearer {access_token()}"},
            json=payload,
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        # Daraja packs the real reason in the body — surface it, not just a code.
        detail = ""
        try:
            detail = e.response.json().get("errorMessage", "")
        except Exception:
            pass
        raise MpesaError(f"STK Push failed (HTTP {e.response.status_code}). {detail}".strip()) from e
    except httpx.RequestError as e:
        raise MpesaError(f"Could not reach M-Pesa (STK Push): {e}") from e

    data = resp.json()
    # ResponseCode "0" = the prompt was accepted for delivery. Anything else is a
    # request-time rejection (bad shortcode, throttling, etc.).
    if str(data.get("ResponseCode")) != "0":
        raise MpesaError(data.get("ResponseDescription") or "STK Push was rejected.")
    return {
        "checkout_request_id": data.get("CheckoutRequestID"),
        "merchant_request_id": data.get("MerchantRequestID"),
        "customer_message": data.get("CustomerMessage"),
    }


# ── SMOKE TEST ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    #   backend/.venv/Scripts/python -m app.services.mpesa
    # Proves OAuth works against Daraja with the real .env credentials (no charge).
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"Env: {settings.mpesa_env}  →  {settings.mpesa_base_url}")
    try:
        tok = access_token()
        print(f"OAuth OK — token starts {tok[:12]}… (len {len(tok)})")
    except MpesaError as e:
        sys.exit(f"OAuth FAILED: {e}")
