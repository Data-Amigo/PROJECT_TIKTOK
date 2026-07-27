"""
Order — one customer's attempt to buy a product, tracked through payment.

Lifecycle:   PENDING ──(STK sent, awaiting PIN)──> PAID   (callback: ResultCode 0)
                    └────────────────────────────> FAILED (callback: anything else)

The state machine exists so money is ALWAYS tracked before it moves: we create
the PENDING order, THEN ask M-Pesa for the prompt. Whether it actually paid is
told to us later by Safaricom's callback — never assumed. "Callback = truth."

Rails baked in here:
  - amount_kes is a SNAPSHOT set from the product price server-side — never from
    the buyer or the agent (the "code disposes" money rail).
  - product_name is snapshotted too, so an order stays self-describing even if
    the product is later edited or removed.
  - only a PENDING order may transition (see services/orders.py), which makes the
    callback idempotent — Safaricom can fire it twice and stock drops just once.
"""

import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class OrderStatus(str, enum.Enum):
    """String-valued so it JSON-serializes for free and reads well in SQL."""

    PENDING = "pending"  # STK prompt sent; waiting on the buyer's PIN / the callback
    PAID = "paid"        # callback confirmed payment (ResultCode 0)
    FAILED = "failed"    # callback said not paid (wrong PIN, cancelled, timed out)


class Order(Base):
    __tablename__ = "orders"

    __table_args__ = (
        # Money and quantity are always positive — the DB refuses anything else.
        CheckConstraint("amount_kes > 0", name="ck_orders_amount_positive"),
        CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # What was bought + from whom. SET NULL (not CASCADE): an order is a financial
    # record — deleting a product or seller must never erase the payment history.
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True, nullable=True
    )
    seller_id: Mapped[int | None] = mapped_column(
        ForeignKey("sellers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Snapshot so the order self-describes even if the product later changes/goes.
    product_name: Mapped[str] = mapped_column(String(120), default="")

    # Who pays — canonical 2547XXXXXXXX (normalized at the border).
    buyer_phone: Mapped[str] = mapped_column(String(15))

    # Snapshot of price × quantity at order time. INTEGER shillings (see Product).
    amount_kes: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=OrderStatus.PENDING,
        index=True,
    )

    # ── M-Pesa linkage (how the callback finds this order) ────────────────────
    # Daraja's id for the STK request. UNIQUE + indexed: the callback looks the
    # order up by exactly this. Null until the STK push is accepted.
    checkout_request_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    merchant_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The M-Pesa confirmation code (e.g. "QGH7XYZ12A"), set from the callback on
    # success — the buyer's and seller's proof of payment.
    mpesa_receipt: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Raw callback result, kept for diagnosing failures.
    result_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_desc: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product = relationship("Product")
    seller = relationship("Seller")

    def __repr__(self) -> str:
        return f"<Order id={self.id} {self.product_name!r} KES{self.amount_kes} {self.status.value}>"
