"""
Products + Pages HTTP routes.

    /api/products/ingest        POST   scrape a handle → DRAFT products
    /api/products/{id}/autofill POST   run the 🤖 vision agent on one product
    /api/products/{id}          PATCH  seller sets words/price/stock, publishes
    /api/pages/{handle}         GET    public bob.link/<handle> data (buyers)

Routes are thin: call a service, map its exceptions to HTTP. All the meaning
lives in services/products.py.
"""

# Lazy annotations: lets us name ORM types (Product) in return hints without
# importing them just for the annotation — they're strings until something asks.
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agent.draft import DraftError
from app.db import get_db
from app.models.product import Product
from app.schemas.product import (
    AutofillOut,
    IngestIn,
    ProductOut,
    ProductPublicOut,
    ProductUpdateIn,
    PublicPageOut,
)
from app.services import products as svc
from app.services.scraper import ScraperError

router = APIRouter(prefix="/api/products", tags=["products"])
pages_router = APIRouter(prefix="/api/pages", tags=["pages"])


# ── Seller-facing ─────────────────────────────────────────────────────────────
@router.post("/ingest", response_model=list[ProductOut], status_code=status.HTTP_201_CREATED)
def ingest(body: IngestIn, db: Session = Depends(get_db)) -> list[Product]:
    """Paste a handle → we scrape recent videos into DRAFT products."""
    try:
        return svc.ingest_seller_videos(db, body.handle, limit=body.limit)
    except ScraperError as e:
        # Upstream (Apify/TikTok) couldn't give us usable data → 502, not 500:
        # our service is fine, the dependency failed. Message is human-safe.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e


@router.post("/{product_id}/autofill", response_model=AutofillOut)
def autofill(product_id: int, db: Session = Depends(get_db)) -> AutofillOut:
    """Run the vision draft agent on one product (fills name + description)."""
    try:
        product, tags, note = svc.autofill_product(db, product_id)
    except svc.ProductError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except DraftError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return AutofillOut(product=ProductOut.model_validate(product), suggested_tags=tags, language_note=note)


@router.patch("/{product_id}", response_model=ProductOut)
def update(product_id: int, body: ProductUpdateIn, db: Session = Depends(get_db)) -> Product:
    """Seller confirms a draft: edit words, set price + stock, optionally publish."""
    try:
        return svc.update_product(db, product_id, body)
    except svc.ProductError as e:
        # "not found" and "can't publish without price" both land here; 400 is
        # the honest catch-all for a rejected business request (the client sent
        # something we won't do). 404-vs-400 nuance isn't worth leaking detail.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


# ── Buyer-facing ──────────────────────────────────────────────────────────────
@pages_router.get("/{handle}", response_model=PublicPageOut)
def public_page(handle: str, db: Session = Depends(get_db)) -> PublicPageOut:
    """The whole public shop page for bob.link/<handle>."""
    try:
        seller = svc.get_public_page(db, handle)
    except svc.ProductError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    return PublicPageOut(
        handle=seller.handle,
        display_name=seller.display_name,
        avatar_url=seller.avatar_url,
        products=[ProductPublicOut.model_validate(p) for p in svc.public_products(seller)],
    )
