"""
Product — one sellable item, born from a scraped TikTok video.

Lifecycle:   scrape ──> DRAFT (LLM-suggested name/desc, no price yet)
                          │  seller confirms name, sets price + stock
                          ▼
                       PUBLISHED (visible on the public page)

Availability is NOT a column — it's derived (stock > 0) so it can never
disagree with reality. Store facts, compute states.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ProductStatus(str, enum.Enum):
    """String-valued so it JSON-serializes for free and reads well in SQL."""

    DRAFT = "draft"          # scraped + LLM-drafted, awaiting seller review
    PUBLISHED = "published"  # live on the public page


class Product(Base):
    __tablename__ = "products"

    # DB-level rails — enforced no matter which code path writes:
    __table_args__ = (
        # The overselling rail: negative stock is physically unrecordable.
        # Payment callbacks decrement stock; even a double-fired callback
        # cannot push it below zero — the DB refuses the write.
        CheckConstraint("stock >= 0", name="ck_products_stock_non_negative"),
        # A published product must carry a price. Drafts may not have one yet
        # (the LLM never sets prices — the seller does, at publish time).
        CheckConstraint(
            "status != 'published' OR price_kes IS NOT NULL",
            name="ck_products_published_needs_price",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Owner. Indexed: the dashboard and public page both ask "this seller's
    # products" constantly. CASCADE matches the relationship in seller.py.
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )

    # ── Scrape identity (idempotency rail) ────────────────────────────────
    # TikTok's own video id (e.g. "7665294006422654226"). UNIQUE: re-scraping
    # the same video updates the existing row, never duplicates it. The DB
    # owns uniqueness because every code path must obey it.
    tiktok_video_id: Mapped[str] = mapped_column(String(30), unique=True)

    video_url: Mapped[str] = mapped_column(Text)

    # Raw caption + hashtags, kept verbatim (evidence, not scratch space).
    # Spike 00: captions are hashtag soup, but hashtags carry weak category
    # hints (#duvets, #bathmat) the draft agent uses.
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list] = mapped_column(JSONB, default=list)

    # OUR stored copy of the cover image (TikTok CDN links expire — the #1
    # spike-00 gotcha). This is what the vision LLM reads and buyers see.
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Listing (LLM drafts, seller confirms) ─────────────────────────────
    name: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")

    # ── Money + stock (deterministic, human-set — NEVER LLM-set) ──────────
    # Whole Kenyan shillings as an INTEGER. Floats corrupt money (0.1+0.2
    # problems), and M-Pesa transacts whole shillings anyway. If fractions
    # ever matter, the answer is integer cents — never float.
    price_kes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    stock: Mapped[int] = mapped_column(Integer, default=0)

    # native_enum=False → stored as VARCHAR + app-side enum, because native
    # Postgres enums turn "add a status" into a special migration ritual.
    # Same type safety in Python, none of the operational pain.
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=ProductStatus.DRAFT,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # onupdate is app-side (SQLAlchemy sets it on UPDATE) — fine for "when
    # did the listing last change", not for anything money-critical.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    seller = relationship("Seller", back_populates="products")

    @property
    def is_available(self) -> bool:
        """Derived, never stored: availability = published with stock left.
        A stored 'available' flag could drift from stock; a computed one
        cannot. Store facts, compute states."""
        return self.status == ProductStatus.PUBLISHED and self.stock > 0

    def __repr__(self) -> str:
        return f"<Product {self.name!r} (id={self.id}, stock={self.stock}, {self.status.value})>"
