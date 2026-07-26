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

from app.agent import sales
from app.agent.draft import DraftError, DraftQuotaError
from app.api.deps import get_current_account
from app.db import get_db
from app.models.account import Account
from app.models.product import Product
from app.schemas.chat import ChatIn, ChatOut
from app.schemas.product import (
    AutodraftOut,
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


@router.post("/autodraft", response_model=AutodraftOut)
def autodraft(
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> AutodraftOut:
    """Auto-draft all of the seller's un-drafted products (name/description +
    a price the AI can read). Best-effort; `ai_paused` if the daily cap stopped
    it. The seller only reviews + publishes."""
    products, ai_paused = svc.autodraft_account(db, account)
    return AutodraftOut(
        products=[ProductOut.model_validate(p) for p in products],
        ai_paused=ai_paused,
    )


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


@pages_router.post("/{handle}/chat", response_model=ChatOut)
def shop_chat(handle: str, body: ChatIn, db: Session = Depends(get_db)) -> ChatOut:
    """The 💬 sales agent: answers a buyer's question from THIS shop's catalogue.
    Public (buyers aren't logged in). Answers only — the M-Pesa 'Buy Now' is M4."""
    try:
        seller = svc.get_public_page(db, handle)
    except svc.ProductError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    # A conversation must start with a buyer turn (the greeting is UI-only).
    if body.messages[0].role != "user":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Conversation must start with a customer message.")

    published = svc.public_products(seller)
    catalogue = [
        sales.CatalogueItem(
            name=p.name or "Untitled",
            price_kes=p.price_kes,
            available=p.is_available,
            description=p.description,
        )
        for p in published
    ]
    featured = None
    if body.video_id:
        match = next((p for p in published if p.tiktok_video_id == body.video_id), None)
        if match is not None:
            featured = sales.CatalogueItem(
                name=match.name or "Untitled",
                price_kes=match.price_kes,
                available=match.is_available,
                description=match.description,
            )

    history = [{"role": m.role, "content": m.content} for m in body.messages]
    try:
        reply = sales.answer(seller.display_name, catalogue, history, featured)
    except sales.SalesError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return ChatOut(reply=reply)
