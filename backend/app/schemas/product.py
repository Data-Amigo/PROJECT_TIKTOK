"""
Product API schemas — request/response shapes for the products + pages routes.

Naming convention: `*In` = request body (what the client sends),
`*Out` = response body (what we return). ORM objects become `*Out` via
`from_attributes` (pydantic reads model attributes directly).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.product import ProductStatus


# ── Requests ──────────────────────────────────────────────────────────────────
class IngestIn(BaseModel):
    """Seller pastes their TikTok handle (or a profile URL — the scraper
    normalizes either). We scrape their recent videos into DRAFT products."""

    handle: str = Field(min_length=1, description="TikTok handle, @handle, or profile URL")
    limit: int = Field(default=6, ge=1, le=20, description="How many recent videos to pull")


class ProductUpdateIn(BaseModel):
    """Seller confirming a draft: edit the words, set the money, optionally
    publish. Every field optional — this is a PATCH (change only what's sent).

    price_kes and stock have validation floors here AND a DB CheckConstraint
    behind them (belt and suspenders — the API rejects bad input early with a
    clear message; the DB refuses it no matter what path writes)."""

    name: str | None = Field(default=None, max_length=120)
    description: str | None = None
    price_kes: int | None = Field(default=None, gt=0, description="Whole shillings; must be positive")
    stock: int | None = Field(default=None, ge=0)
    publish: bool = Field(default=False, description="Flip DRAFT → PUBLISHED (requires a price)")


# ── Responses ─────────────────────────────────────────────────────────────────
class ProductOut(BaseModel):
    """Full product view — the dashboard (seller's own) sees everything."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tiktok_video_id: str
    video_url: str
    cover_url: str | None
    name: str
    description: str
    price_kes: int | None
    stock: int
    status: ProductStatus
    is_available: bool
    created_at: datetime


class AutofillOut(BaseModel):
    """Result of running the vision draft agent on one product. The product is
    now filled with a suggested name/description; `suggested_tags` are returned
    for display only (we don't persist them — no column, and they're a hint)."""

    product: ProductOut
    suggested_tags: list[str] = []
    language_note: str = ""


# ── Public page (what BUYERS see — deliberately narrower) ─────────────────────
class ProductPublicOut(BaseModel):
    """Buyer-facing product card. Note what's ABSENT vs ProductOut: no draft
    status, no tiktok_video_id, no timestamps. The public shape only exposes
    what a shopper needs — leaking internal fields is how APIs grow liabilities."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cover_url: str | None
    name: str
    description: str
    price_kes: int | None
    is_available: bool


class PublicPageOut(BaseModel):
    """The whole bob.link/<handle> page in one response."""

    model_config = ConfigDict(from_attributes=True)

    handle: str
    display_name: str
    avatar_url: str | None
    products: list[ProductPublicOut]
