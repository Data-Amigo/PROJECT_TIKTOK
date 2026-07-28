"""
Customers service — capture a buyer's contact from the sales chat. (M5.2)

The bot extracts a name + phone from the conversation; this persists it as ONE
row per (seller, phone). Deterministic + owns the phone-normalization rule, so
the chat route stays thin.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.seller import Seller
from app.utils import normalize_kenyan_phone


def capture_customer(db: Session, seller: Seller, name: str | None, phone: str | None) -> Customer | None:
    """Upsert a captured customer. Returns the row, or None if the phone isn't a
    valid Kenyan number (we never store a half-captured/garbage contact).

    Idempotent by (seller, phone): the same buyer messaging again updates their
    name instead of duplicating."""
    if not phone:
        return None
    try:
        canonical = normalize_kenyan_phone(phone)
    except ValueError:
        return None  # the bot misread a 'phone' — skip rather than store junk

    clean_name = (name or "").strip()[:120]
    existing = db.scalar(
        select(Customer).where(Customer.seller_id == seller.id, Customer.phone == canonical)
    )
    if existing is not None:
        if clean_name and clean_name != existing.name:
            existing.name = clean_name  # fill in / correct the name on a repeat
        customer = existing
    else:
        customer = Customer(seller_id=seller.id, name=clean_name, phone=canonical)
        db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer
