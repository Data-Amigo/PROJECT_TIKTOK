"""
Daraja (M-Pesa) webhook — where Safaricom reports a payment result. (M4.3)

    POST /api/daraja/callback   ← Safaricom posts the STK result here

This is the "callback = truth" endpoint: an order becomes PAID only from here,
never from the checkout response. Two rules make it safe:
  1. IDEMPOTENT — the service only transitions a PENDING order, so Safaricom
     retrying the callback changes nothing (and stock drops exactly once).
  2. ALWAYS ACK 200 — even on a bad/unknown body we return Daraja's expected
     acknowledgement, so it stops retrying. We never leak internals to Safaricom.

This URL is public and unauthenticated (Safaricom can't send a bearer token).
That's acceptable because the callback only SETTLES an order WE already created
with a checkout_request_id WE got from Daraja — a forged callback for a random
id matches no pending order and is a no-op. (Hardening: IP allow-list / a
confirmation query to Daraja can come later.)
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import orders as order_svc

router = APIRouter(prefix="/api/daraja", tags=["daraja"])

# Daraja expects exactly this shape back, and a 200, or it keeps retrying.
_ACK = {"ResultCode": 0, "ResultDesc": "Accepted"}


@router.post("/callback")
async def stk_callback(request: Request, db: Session = Depends(get_db)) -> dict:
    """Receive an STK result and settle the order. Never raises to Safaricom."""
    try:
        payload = await request.json()
    except Exception:
        return _ACK  # unparseable body — ack anyway so Daraja stops retrying
    try:
        order_svc.handle_stk_callback(db, payload)
    except Exception:
        # A processing bug must not make us NACK and trigger endless retries.
        # (Real logging goes here; the order simply stays PENDING for a human.)
        pass
    return _ACK
