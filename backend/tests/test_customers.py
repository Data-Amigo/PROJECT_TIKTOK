"""Customer capture — dedup by (seller, phone), normalize, skip garbage."""

import itertools

from sqlalchemy import func, select

from app.models.account import Account
from app.models.customer import Customer
from app.models.seller import Seller
from app.security import hash_password
from app.services import customers as svc

_seq = itertools.count(1)


def _seller(db) -> Seller:
    i = next(_seq)
    a = Account(name=f"S{i}", email=f"cust{i}@example.com", phone=f"2547{i:08d}", password_hash=hash_password("password8"))
    db.add(a)
    db.flush()
    s = Seller(account_id=a.id, handle=f"custshop{i}", display_name="Shop", tiktok_username=f"tt{i}")
    db.add(s)
    db.flush()
    return s


def test_capture_normalizes_and_dedupes_by_phone(db_session):
    s = _seller(db_session)
    c1 = svc.capture_customer(db_session, s, "Aisha", "0712345678")
    assert c1.phone == "254712345678" and c1.name == "Aisha"

    # Same person, different format + a corrected name → same row, name updated.
    c2 = svc.capture_customer(db_session, s, "Aisha W", "+254712345678")
    assert c2.id == c1.id and c2.name == "Aisha W"

    count = db_session.scalar(
        select(func.count()).select_from(Customer).where(Customer.seller_id == s.id)
    )
    assert count == 1


def test_capture_skips_an_invalid_phone(db_session):
    s = _seller(db_session)
    assert svc.capture_customer(db_session, s, "Bob", "not-a-number") is None
    assert svc.capture_customer(db_session, s, "Bob", None) is None
    count = db_session.scalar(
        select(func.count()).select_from(Customer).where(Customer.seller_id == s.id)
    )
    assert count == 0


def test_capture_stores_phone_even_before_a_name(db_session):
    # Phone can arrive before the name; we still capture, name fills in later.
    s = _seller(db_session)
    c = svc.capture_customer(db_session, s, None, "0722000111")
    assert c is not None and c.phone == "254722000111" and c.name == ""
