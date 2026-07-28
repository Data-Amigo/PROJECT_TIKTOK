"""
Storefront service — connect a TikTok account to a seller's SokoLink shop.

    connect(username) ──▶ scrape profile (ONE pass) ──▶ upsert storefront profile
                                                    └──▶ upsert draft products
The single scrape both hydrates the shop profile (name/avatar/bio/followers)
AND pulls the recent videos into DRAFT products — matching the account-first
flow: "connect once → your content shows up as products to confirm."

Ownership rules enforced here:
  - one account owns one storefront (Seller.account_id is unique)
  - a TikTok username already owned by ANOTHER account can't be connected
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.product import Product
from app.models.seller import Seller
from app.services import scraper

# How many recent videos to pull into drafts on connect/refresh.
SYNC_LIMIT = 8


class StorefrontError(Exception):
    """A connect/business-rule failure with a message safe to show a human."""


def _unique_handle(db: Session, base: str) -> str:
    """Turn a TikTok username into a unique public handle (sokolink/<handle>).
    Lower-cased, url-safe; appends -2, -3… if the slug is already taken."""
    slug = re.sub(r"[^a-z0-9_.]", "", base.lower()) or "shop"
    candidate = slug
    n = 1
    while db.scalar(select(Seller).where(Seller.handle == candidate)):
        n += 1
        candidate = f"{slug}-{n}"
    return candidate


def get_storefront(db: Session, account: Account) -> Seller | None:
    """The account's storefront, or None if they haven't connected TikTok yet."""
    return db.scalar(select(Seller).where(Seller.account_id == account.id))


def connect_tiktok(db: Session, account: Account, username: str) -> Seller:
    """Connect (or re-point) the account's storefront to a TikTok username:
    scrape, hydrate the profile, and pull recent videos into DRAFT products."""
    username = scraper.normalize_username(username)

    # Scrape once — validates the handle AND gives us author meta + videos.
    videos = scraper.fetch_profile(username, limit=SYNC_LIMIT)  # raises ScraperError
    author = videos[0].authorMeta

    # Guard: is this TikTok already owned by a DIFFERENT account?
    clash = db.scalar(select(Seller).where(Seller.tiktok_username == username))
    if clash is not None and clash.account_id not in (None, account.id):
        raise StorefrontError(
            "That TikTok account is already connected to another SokoLink shop."
        )

    seller = get_storefront(db, account)

    # Compute the handle BEFORE the new seller is pending in the session — the
    # uniqueness query below autoflushes, and a half-built seller (handle NOT
    # NULL) would blow up mid-flush. Existing shops keep their handle (stable URL).
    handle = seller.handle if seller is not None else _unique_handle(db, username)

    if seller is None:
        seller = Seller(account_id=account.id, handle=handle)
        db.add(seller)

    # Auto-fill the storefront profile from TikTok (the seller can edit later).
    seller.handle = handle
    seller.tiktok_username = username
    seller.display_name = author.nickName or author.name
    seller.bio = author.signature
    seller.follower_count = author.fans
    seller.phone = account.phone            # the M-Pesa/contact number from signup
    try:
        avatar = scraper.save_avatar(username, author.avatar)
        if avatar:
            seller.avatar_url = avatar
    except scraper.ScraperError:
        pass  # avatar is nice-to-have; a failed download must not block connect

    db.flush()  # assign seller.id before attaching products

    # Upsert the scraped videos as DRAFT products (idempotent by video id).
    _upsert_products(db, seller, videos)

    db.commit()
    db.refresh(seller)
    return seller


def refresh(db: Session, account: Account) -> Seller:
    """Re-pull the connected account's latest videos (same sync, existing name)."""
    seller = get_storefront(db, account)
    if seller is None or not seller.tiktok_username:
        raise StorefrontError("Connect your TikTok first.")
    return connect_tiktok(db, account, seller.tiktok_username)


def _upsert_products(db: Session, seller: Seller, videos) -> None:
    """Create/refresh DRAFT products from scraped videos. Never touches
    name/description/price/stock — those are seller-owned once set."""
    for v in videos:
        product = db.scalar(select(Product).where(Product.tiktok_video_id == v.id))
        if product is None:
            product = Product(tiktok_video_id=v.id, seller_id=seller.id)
            db.add(product)
        product.video_url = v.webVideoUrl
        product.caption = v.text
        product.hashtags = v.hashtags
        product.video_download_url = v.video_download_url  # for the price fallback
        try:
            cover = scraper.save_cover(v)
            if cover:
                product.cover_url = cover
        except scraper.ScraperError:
            pass  # keep any prior cover; a download blip won't sink the sync
