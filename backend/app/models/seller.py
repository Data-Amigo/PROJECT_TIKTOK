"""
Seller — the shop owner. One row per pilot seller.

Field choices trace to spike 00 (real kinjobales_wholesale data):
the TikTok bio carried shop addresses + phone numbers, so we keep the raw
bio as onboarding source material and auto-fill from it later.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Seller(Base):
    __tablename__ = "sellers"

    # Internal identity — integer PK stays private to us; the PUBLIC identity
    # is `handle` below. Never leak DB ids into URLs.
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The bob.link/<handle> slug. Unique + indexed because the public page
    # looks sellers up by it on every single view.
    handle: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    # What buyers see on the page ("Mama Wanjiku Collections").
    display_name: Mapped[str] = mapped_column(String(100))

    # Their TikTok username (authorMeta.name in the Apify payload). Unique:
    # one BOB seller per TikTok account — a second registration is a mistake
    # or an impersonation, and the DB should refuse both. Nullable because a
    # seller can be created before their TikTok is connected.
    tiktok_username: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )

    # RAW bio text, exactly as scraped. Spike 00 showed it holds addresses +
    # phones ("kampala center ... 0727910437"). We parse COPIES from it and
    # never overwrite it — source data is evidence, not scratch space.
    bio: Mapped[str] = mapped_column(Text, default="")

    # Seller's own M-Pesa/contact number, normalized to 2547XXXXXXXX when we
    # store it. Nullable until onboarding confirms it (auto-fill suggests,
    # the human confirms — same rule as prices).
    phone: Mapped[str | None] = mapped_column(String(15), nullable=True)

    # OUR stored copy of their avatar (TikTok CDN URLs expire — spike 00).
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # DB-clock timestamp (timezone=True → stored as timestamptz). App-server
    # clocks drift and lie; the database's clock is the one shared truth.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ORM convenience: seller.products / product.seller. delete-orphan means
    # deleting a seller through the ORM removes their products too — matches
    # the FK's ON DELETE CASCADE so ORM and DB agree on the rules.
    products = relationship(
        "Product", back_populates="seller", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # human-friendly in logs and the debugger
        return f"<Seller {self.handle!r} (id={self.id})>"
