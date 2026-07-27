"""
Orders service — the deterministic rails around a payment. (M4.2/4.3)

    start_checkout ──> create PENDING order ──> mpesa.stk_push ──> prompt sent
    handle_stk_callback ──> PENDING → PAID/FAILED (idempotent) ──> stock drops once

Everything money-critical lives here, on purpose:
  - the AMOUNT is computed from the product's price server-side (never the buyer);
  - availability/price are re-checked at checkout time (not trusted from the UI);
  - only a PENDING order transitions, so a duplicate callback is a no-op and
    stock is decremented exactly once. "Callback = truth."
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.product import Product, ProductStatus
from app.models.seller import Seller
from app.services import mpesa
from app.utils import normalize_kenyan_phone


class OrderError(Exception):
    """A checkout that can't proceed, with a message safe to show a buyer."""


def start_checkout(db: Session, handle: str, product_id: int, phone: str, quantity: int = 1) -> Order:
    """Create a PENDING order and fire the M-Pesa STK prompt.

    Guards (all re-checked here — the UI is never trusted): the product exists
    under THIS shop, is published, has a price, and has enough stock. Returns the
    order with its checkout_request_id. Raises OrderError (bad request) or
    mpesa.MpesaError (payment provider down) — the API maps each to a status."""
    seller = db.scalar(select(Seller).where(Seller.handle == handle))
    if seller is None:
        raise OrderError(f"No shop at /{handle}.")

    product = db.scalar(
        select(Product).where(Product.id == product_id, Product.seller_id == seller.id)
    )
    if product is None:
        raise OrderError("That product isn't in this shop.")
    if product.status != ProductStatus.PUBLISHED:
        raise OrderError("That product isn't on sale.")
    if product.price_kes is None:
        raise OrderError("That product has no price yet.")
    if product.stock < quantity:
        raise OrderError("Sorry, that's sold out." if product.stock == 0 else f"Only {product.stock} left.")

    # Normalize once, here, for storage; stk_push re-normalizes (idempotent).
    try:
        buyer_phone = normalize_kenyan_phone(phone)
    except ValueError as e:
        raise OrderError(str(e)) from e

    # THE money rail: amount comes from the product's own price, never the buyer.
    amount = product.price_kes * quantity

    order = Order(
        product_id=product.id,
        seller_id=seller.id,
        product_name=product.name or "Item",
        buyer_phone=buyer_phone,
        amount_kes=amount,
        quantity=quantity,
        status=OrderStatus.PENDING,
    )
    db.add(order)
    db.flush()  # assign order.id so it can be the AccountReference

    try:
        ack = mpesa.stk_push(
            phone=buyer_phone,
            amount=amount,
            account_reference=f"SL{order.id}",
            description=(product.name or "Order")[:13],
        )
    except mpesa.MpesaError:
        # The prompt never went out — record the failure and re-raise for the API.
        order.status = OrderStatus.FAILED
        order.result_desc = "STK push not sent"
        db.commit()
        raise

    order.checkout_request_id = ack["checkout_request_id"]
    order.merchant_request_id = ack["merchant_request_id"]
    db.commit()
    return order


def get_order(db: Session, order_id: int) -> Order | None:
    return db.get(Order, order_id)


def handle_stk_callback(db: Session, payload: dict) -> None:
    """Apply Safaricom's STK result to the matching order. IDEMPOTENT: only a
    PENDING order transitions, so a duplicate callback changes nothing and stock
    drops exactly once. Never raises — an unknown/duplicate callback is a no-op
    (the endpoint always acks 200 so Daraja stops retrying)."""
    stk = (payload or {}).get("Body", {}).get("stkCallback", {})
    checkout_id = stk.get("CheckoutRequestID")
    if not checkout_id:
        return

    order = db.scalar(select(Order).where(Order.checkout_request_id == checkout_id))
    if order is None or order.status != OrderStatus.PENDING:
        return  # unknown, or already settled — ignore

    try:
        result_code = int(stk.get("ResultCode", -1))
    except (TypeError, ValueError):
        result_code = -1
    order.result_code = result_code
    order.result_desc = (stk.get("ResultDesc") or "")[:255]

    if result_code == 0:
        # Success: pull the receipt from the metadata items, mark paid, drop stock.
        meta = {i.get("Name"): i.get("Value") for i in stk.get("CallbackMetadata", {}).get("Item", [])}
        receipt = meta.get("MpesaReceiptNumber")
        order.mpesa_receipt = str(receipt)[:32] if receipt else None
        order.status = OrderStatus.PAID
        if order.product is not None:
            # DB CheckConstraint stock>=0 is the final backstop; max() keeps us
            # off it even in a weird double-count.
            order.product.stock = max(order.product.stock - order.quantity, 0)
    else:
        order.status = OrderStatus.FAILED

    db.commit()
