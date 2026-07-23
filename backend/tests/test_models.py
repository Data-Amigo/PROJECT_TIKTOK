"""
Model tests — prove the data spine's claims, especially the DB-level rails.

Philosophy: we don't test that SQLAlchemy works (it does); we test OUR
rules — constraints, derived availability, the idempotency rail — because
those are the claims the rest of BOB will lean on.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Product, ProductStatus, Seller


def make_seller(**overrides) -> Seller:
    """Small factory so tests state only what they care about."""
    defaults = dict(handle="mama-wanjiku", display_name="Mama Wanjiku Collections")
    return Seller(**{**defaults, **overrides})


def make_product(seller: Seller, **overrides) -> Product:
    defaults = dict(
        seller=seller,
        tiktok_video_id="7665294006422654226",  # real id from spike 00
        video_url="https://www.tiktok.com/@kinjobales_wholesale/video/7665294006422654226",
        hashtags=["duvets", "kenyantiktok"],
        name="Cotton Duvet 6x6",
    )
    return Product(**{**defaults, **overrides})


def test_seller_product_round_trip(db_session):
    """The basic promise: what we write is what we read, relationship intact."""
    seller = make_seller()
    product = make_product(seller)
    db_session.add(seller)          # product rides along via the relationship
    db_session.flush()              # send SQL, get ids — still inside the txn

    fetched = db_session.get(Product, product.id)
    assert fetched.seller.handle == "mama-wanjiku"
    assert fetched.hashtags == ["duvets", "kenyantiktok"]  # JSONB survived
    assert fetched.status == ProductStatus.DRAFT           # default applied
    assert fetched.created_at is not None                  # DB clock stamped it


def test_availability_is_derived_not_stored(db_session):
    """is_available = published AND stock > 0 — both conditions must hold."""
    seller = make_seller()
    p = make_product(seller, status=ProductStatus.PUBLISHED, price_kes=800, stock=3)
    db_session.add(seller)
    db_session.flush()

    assert p.is_available is True
    p.stock = 0
    assert p.is_available is False          # sold out
    p.stock = 5
    p.status = ProductStatus.DRAFT
    assert p.is_available is False          # not published = not available


def test_duplicate_tiktok_video_is_refused(db_session):
    """The idempotency rail: same video twice → the DATABASE says no."""
    seller = make_seller()
    db_session.add(seller)
    db_session.add(make_product(seller))
    db_session.flush()

    db_session.add(make_product(seller))    # same tiktok_video_id again
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_negative_stock_is_refused(db_session):
    """The overselling rail: not 'code shouldn't do this' — code CANNOT."""
    seller = make_seller()
    db_session.add(seller)
    db_session.add(make_product(seller, stock=-1))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_publishing_without_price_is_refused(db_session):
    """The no-free-goods rail: published + NULL price → refused by the DB.
    (This is the constraint that guarantees the LLM can never push an
    unpriced draft live — publishing REQUIRES the human-set price.)"""
    seller = make_seller()
    db_session.add(seller)
    db_session.add(make_product(seller, status=ProductStatus.PUBLISHED, price_kes=None))
    with pytest.raises(IntegrityError):
        db_session.flush()
