"""
Orders HTTP routes — the buyer's payment-status polling.

    GET /api/orders/{id}   is my payment done yet? (pending → paid/failed)

Public: the buyer isn't logged in, and the id is the one we just handed them at
checkout. It exposes only the order's own status/receipt (see OrderStatusOut).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.order import OrderStatusOut
from app.services import orders as order_svc

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("/{order_id}", response_model=OrderStatusOut)
def get_order(order_id: int, db: Session = Depends(get_db)) -> OrderStatusOut:
    order = order_svc.get_order(db, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such order.")
    return OrderStatusOut(
        id=order.id,
        status=order.status.value,
        product_name=order.product_name,
        amount_kes=order.amount_kes,
        mpesa_receipt=order.mpesa_receipt,
    )
