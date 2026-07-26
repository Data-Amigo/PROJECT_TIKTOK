"""
Account routes — the seller managing their own shop (all require login).

    POST /api/account/connect-tiktok   connect a TikTok username → storefront
    GET  /api/account/storefront       the account's storefront, or null
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.db import get_db
from app.models.account import Account
from app.schemas.storefront import ConnectTikTokIn, StorefrontOut
from app.services import storefront as svc
from app.services.scraper import ScraperError

router = APIRouter(prefix="/api/account", tags=["account"])


@router.post("/connect-tiktok", response_model=StorefrontOut)
def connect_tiktok(
    body: ConnectTikTokIn,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> StorefrontOut:
    """Scrape the TikTok, build the storefront profile, pull recent videos."""
    try:
        seller = svc.connect_tiktok(db, account, body.username)
    except svc.StorefrontError as e:
        # e.g. username owned by another shop → 409 Conflict.
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ScraperError as e:
        # Upstream (Apify/TikTok) couldn't return usable data → 502.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return StorefrontOut.model_validate(seller)


@router.get("/storefront", response_model=StorefrontOut | None)
def storefront(
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> StorefrontOut | None:
    """The account's storefront, or null if they haven't connected TikTok yet.
    The dashboard uses this to decide: show the connect screen, or the shop."""
    seller = svc.get_storefront(db, account)
    return StorefrontOut.model_validate(seller) if seller else None
