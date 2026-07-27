"""
Order / checkout API schemas.

Note what the buyer's CheckoutIn does NOT contain: a price. The amount is set
server-side from the product's own price (the "code disposes" money rail) — a
buyer can't propose what they pay.
"""

from pydantic import BaseModel, ConfigDict, Field


class CheckoutIn(BaseModel):
    """A buyer starting a purchase from the public page."""

    product_id: int = Field(description="Which published product they're buying")
    phone: str = Field(min_length=9, max_length=15, description="M-Pesa number, any format — normalized to 2547…")
    quantity: int = Field(default=1, ge=1, le=100)


class CheckoutOut(BaseModel):
    """Acknowledgement that the STK prompt was SENT — not that payment happened.
    The UI then polls GET /api/orders/{id} for the paid/failed result."""

    order_id: int
    status: str
    customer_message: str


class OrderStatusOut(BaseModel):
    """What the buyer's 'waiting for payment' screen polls."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    product_name: str
    amount_kes: int
    mpesa_receipt: str | None = None
