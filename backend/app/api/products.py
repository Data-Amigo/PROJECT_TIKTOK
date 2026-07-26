"""
Products + Pages HTTP routes.

    GET   /api/products/mine        the logged-in seller's products (dashboard)
    POST  /api/products/refresh     re-pull the connected TikTok's latest videos
    POST  /api/products/{id}/autofill  run the 🤖 vision agent on one product
    PATCH /api/products/{id}        seller sets words/price/stock, publishes
    GET   /api/pages/{handle}       public sokolink/<handle> data (buyers — no auth)

Every /api/products/* route requires login and is scoped to the caller's own
storefront (ownership enforced in the service). Only /api/pages/* is public.
"""

# Lazy annotations: name ORM types (Product) in hints without importing for it.
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agent.draft import DraftError, DraftQuotaError
from app.api.deps import get_current_account
from app.db import get_db
from app.models.account import Account
from app.models.product import Product
from app.schemas.product import (
    AutofillOut,
    ProductOut,
    ProductPublicOut,
    ProductUpdateIn,
    PublicPageOut,
)
from app.services import products as svc
from app.services import storefront as store_svc
from app.services.scraper import ScraperError

router = APIRouter(prefix="/api/products", tags=["products"])
pages_router = APIRouter(prefix="/api/pages", tags=["pages"])


# ── Seller-facing (all require login, all scoped to the caller) ───────────────
@router.get("/mine", response_model=list[ProductOut])
def my_products(
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> list[Product]:
    """The seller's own products — what the dashboard shows on open."""
    return svc.list_account_products(db, account)


@router.post("/refresh", response_model=list[ProductOut])
def refresh(
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> list[Product]:
    """Re-pull the connected TikTok's latest videos into draft products."""
    try:
        store_svc.refresh(db, account)
    except store_svc.StorefrontError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except ScraperError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return svc.list_account_products(db, account)


@router.post("/{product_id}/autofill", response_model=AutofillOut)
def autofill(
    product_id: int,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> AutofillOut:
    """Run the vision draft agent on one of the seller's products."""
    try:
        product, draft = svc.autofill_product(db, account, product_id)
    except svc.ProductError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except DraftQuotaError as e:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(e)) from e
    except DraftError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return AutofillOut(
        product=ProductOut.model_validate(product),
        is_product=draft.is_product,
        not_product_reason=draft.not_product_reason,
        suggested_price_kes=draft.suggested_price_kes,
        suggested_tags=draft.tags,
        language_note=draft.language_note,
    )


@router.patch("/{product_id}", response_model=ProductOut)
def update(
    product_id: int,
    body: ProductUpdateIn,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> Product:
    """Seller confirms one of THEIR drafts: words, price, stock, publish."""
    try:
        return svc.update_product(db, account, product_id, body)
    except svc.ProductError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


# ── Buyer-facing (public, no auth) ────────────────────────────────────────────
@pages_router.get("/{handle}", response_model=PublicPageOut)
def public_page(handle: str, db: Session = Depends(get_db)) -> PublicPageOut:
    """The whole public shop page for sokolink/<handle>."""
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
