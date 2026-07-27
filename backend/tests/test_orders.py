"""
Order / checkout / callback tests — the money rails, verified without spending.

mpesa.stk_push is mocked (no real Daraja call). The focus: the amount comes from
the DB not the buyer, guards reject bad checkouts, and the callback is idempotent
(a duplicate settles nothing twice and stock drops exactly once).
"""

import itertools

import pytest

from app.models.account import Account
from app.models.order import Order, OrderStatus
from app.models.product import Product, ProductStatus
from app.models.seller import Seller
from app.security import hash_password
from app.services import mpesa
from app.services import orders as order_svc

_seq = itertools.count(1)


def _seller(db, handle=None) -> Seller:
    i = next(_seq)
    a = Account(name=f"S{i}", email=f"ord{i}@example.com", phone=f"2547{i:08d}", password_hash=hash_password("password8"))
    db.add(a)
    db.flush()
    s = Seller(account_id=a.id, handle=handle or f"ordshop{i}", display_name="Shop", tiktok_username=f"tt{i}")
    db.add(s)
    db.flush()
    return s


def _product(db, seller, *, price=600, stock=3, status=ProductStatus.PUBLISHED, name="Ripped Jeans") -> Product:
    p = Product(
        tiktok_video_id=f"{next(_seq):019d}", seller_id=seller.id, video_url="https://t/x",
        name=name, price_kes=price, stock=stock, status=status,
    )
    db.add(p)
    db.flush()
    return p


def _ok_ack(**kw):
    return {"checkout_request_id": "ws_CO_1", "merchant_request_id": "m1", "customer_message": "ok"}


def _paid_payload(checkout_id, receipt="QGH1XYZ"):
    return {"Body": {"stkCallback": {
        "MerchantRequestID": "m", "CheckoutRequestID": checkout_id, "ResultCode": 0, "ResultDesc": "ok",
        "CallbackMetadata": {"Item": [
            {"Name": "Amount", "Value": 600},
            {"Name": "MpesaReceiptNumber", "Value": receipt},
            {"Name": "PhoneNumber", "Value": 254712345678},
        ]},
    }}}


def _failed_payload(checkout_id, code=1032):
    return {"Body": {"stkCallback": {"CheckoutRequestID": checkout_id, "ResultCode": code, "ResultDesc": "Cancelled"}}}


# ── Checkout ──────────────────────────────────────────────────────────────────
def test_checkout_creates_pending_order_with_server_priced_amount(client, db_session, monkeypatch):
    s = _seller(db_session, handle="payshop")
    p = _product(db_session, s, price=600, stock=3)
    db_session.commit()

    captured = {}

    def fake_push(*, phone, amount, account_reference, description):
        captured.update(phone=phone, amount=amount, ref=account_reference)
        return _ok_ack()

    monkeypatch.setattr(mpesa, "stk_push", fake_push)
    r = client.post("/api/pages/payshop/checkout", json={"product_id": p.id, "phone": "0712345678", "quantity": 2})
    assert r.status_code == 200

    order = db_session.get(Order, r.json()["order_id"])
    assert order.status == OrderStatus.PENDING
    assert order.amount_kes == 1200          # 600 × 2, from the DB — not the buyer
    assert order.buyer_phone == "254712345678"
    assert order.checkout_request_id == "ws_CO_1"
    assert captured["amount"] == 1200 and captured["phone"] == "254712345678"


def test_checkout_rejects_sold_out(client, db_session, monkeypatch):
    s = _seller(db_session, handle="payshop2")
    p = _product(db_session, s, stock=0)
    db_session.commit()
    monkeypatch.setattr(mpesa, "stk_push", lambda **kw: pytest.fail("must not push a sold-out item"))
    r = client.post("/api/pages/payshop2/checkout", json={"product_id": p.id, "phone": "0712345678"})
    assert r.status_code == 400


def test_checkout_rejects_unpublished(client, db_session, monkeypatch):
    s = _seller(db_session, handle="payshop3")
    p = _product(db_session, s, status=ProductStatus.DRAFT, price=600, stock=3)
    db_session.commit()
    monkeypatch.setattr(mpesa, "stk_push", lambda **kw: pytest.fail("must not push a draft"))
    r = client.post("/api/pages/payshop3/checkout", json={"product_id": p.id, "phone": "0712345678"})
    assert r.status_code == 400


def test_checkout_maps_mpesa_error_to_502_and_marks_failed(client, db_session, monkeypatch):
    s = _seller(db_session, handle="payshop4")
    p = _product(db_session, s, price=600, stock=3)
    db_session.commit()

    def boom(**kw):
        raise mpesa.MpesaError("Daraja down")

    monkeypatch.setattr(mpesa, "stk_push", boom)
    r = client.post("/api/pages/payshop4/checkout", json={"product_id": p.id, "phone": "0712345678"})
    assert r.status_code == 502


# ── Callback (the truth) ──────────────────────────────────────────────────────
def _pending_order(db, seller, product, checkout_id="ws_CO_X", qty=1) -> Order:
    o = Order(
        product_id=product.id, seller_id=seller.id, product_name=product.name,
        buyer_phone="254712345678", amount_kes=product.price_kes * qty, quantity=qty,
        status=OrderStatus.PENDING, checkout_request_id=checkout_id,
    )
    db.add(o)
    db.commit()
    return o


def test_callback_marks_paid_drops_stock_and_is_idempotent(db_session):
    s = _seller(db_session)
    p = _product(db_session, s, price=600, stock=3)
    o = _pending_order(db_session, s, p, checkout_id="ws_CO_PAID")

    order_svc.handle_stk_callback(db_session, _paid_payload("ws_CO_PAID", receipt="QGH1XYZ"))
    db_session.refresh(o)
    db_session.refresh(p)
    assert o.status == OrderStatus.PAID
    assert o.mpesa_receipt == "QGH1XYZ"
    assert p.stock == 2                      # dropped once

    # Duplicate callback (Safaricom retries) — must change nothing.
    order_svc.handle_stk_callback(db_session, _paid_payload("ws_CO_PAID", receipt="QGH1XYZ"))
    db_session.refresh(p)
    assert p.stock == 2                      # NOT dropped again


def test_callback_failure_marks_failed_and_leaves_stock(db_session):
    s = _seller(db_session)
    p = _product(db_session, s, price=600, stock=3)
    o = _pending_order(db_session, s, p, checkout_id="ws_CO_FAIL")

    order_svc.handle_stk_callback(db_session, _failed_payload("ws_CO_FAIL"))
    db_session.refresh(o)
    db_session.refresh(p)
    assert o.status == OrderStatus.FAILED
    assert p.stock == 3                      # untouched


def test_callback_for_unknown_id_is_a_noop(db_session):
    # No matching order → silently ignored, never raises.
    order_svc.handle_stk_callback(db_session, _paid_payload("no-such-checkout"))


def test_callback_endpoint_always_acks(client, db_session):
    r = client.post("/api/daraja/callback", json=_paid_payload("no-such-checkout"))
    assert r.status_code == 200 and r.json()["ResultCode"] == 0
    # Even a garbage body is acked (so Daraja stops retrying).
    r2 = client.post("/api/daraja/callback", json={"unexpected": "shape"})
    assert r2.status_code == 200


def test_order_status_endpoint(client, db_session):
    s = _seller(db_session, handle="statshop")
    p = _product(db_session, s, price=600, stock=3)
    o = _pending_order(db_session, s, p, checkout_id="ws_CO_STAT")
    r = client.get(f"/api/orders/{o.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending" and body["amount_kes"] == 600 and body["product_name"] == "Ripped Jeans"
