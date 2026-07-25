"""
Products service — the business logic behind the products/pages routes.

    route (api/products.py)  ──calls──▶  THIS  ──uses──▶  scraper / draft agent / DB
    (HTTP concerns only)                 (orchestration + rules)

Why a separate layer: routes should only translate HTTP ↔ Python (status
codes, request bodies). Everything that MEANS something — "ingest is
idempotent", "publishing needs a price", "the agent never sets money" — lives
here, where it can be tested without spinning up a web server.

The golden rule this file enforces, from CONCEPTS.md §4: the agent PROPOSES
(name/description), code DISPOSES (price/stock/publish). Autofill can only
touch words; only update_product can touch money, and only the seller drives it.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import draft as draft_agent
from app.models.product import Product, ProductStatus
from app.models.seller import Seller
from app.schemas.product import ProductUpdateIn
from app.services import scraper


class ProductError(Exception):
    """A business-rule failure (not a 500). Routes map it to a 4xx with this
    message — safe to show a human."""


# ── Ingest: scrape a seller's videos into DRAFT products ──────────────────────
def ingest_seller_videos(db: Session, handle: str, limit: int = 6) -> list[Product]:
    """Scrape recent videos and store them as DRAFT products (no AI, no money).

    IDEMPOTENT by tiktok_video_id: paste the same handle twice and existing
    rows are refreshed, never duplicated — the DB's UNIQUE(tiktok_video_id)
    is the ultimate guard; we check first only to update instead of erroring.

    Deliberately does NOT run the vision agent here — drafting is expensive, so
    it's its own on-demand step (autofill_product). Ingest stays fast and cheap.
    """
    videos = scraper.fetch_profile(handle, limit=limit)  # may raise ScraperError

    # One seller per TikTok account (Seller.tiktok_username is UNIQUE). Find or
    # create them from the scraped author metadata.
    author = videos[0].authorMeta
    seller = db.scalar(select(Seller).where(Seller.tiktok_username == author.name))
    if seller is None:
        seller = Seller(
            handle=author.name,                 # bob.link/<handle>; seller can rename later
            display_name=author.nickName or author.name,
            tiktok_username=author.name,
            bio=author.signature,               # raw bio — holds addresses/phones (spike 00)
        )
        db.add(seller)
        db.flush()  # assign seller.id before we attach products to it

    products: list[Product] = []
    for v in videos:
        product = db.scalar(
            select(Product).where(Product.tiktok_video_id == v.id)
        )
        if product is None:
            product = Product(tiktok_video_id=v.id, seller_id=seller.id)
            db.add(product)

        # Refresh scrape-sourced fields on every ingest (source data can change;
        # our copy should track it). Never touch name/description/price/stock —
        # those are seller-owned once set.
        product.video_url = v.webVideoUrl
        product.caption = v.text
        product.hashtags = v.hashtags
        # Store OUR copy of the cover (TikTok URLs expire). Best-effort: a cover
        # download failure must not sink the whole ingest.
        try:
            product.cover_url = scraper.save_cover(v)
        except scraper.ScraperError:
            product.cover_url = product.cover_url  # keep any prior copy; leave as-is

        products.append(product)

    db.commit()
    for p in products:
        db.refresh(p)
    return products


# ── Autofill: run the vision draft agent on ONE product (the 🤖 step) ─────────
def autofill_product(db: Session, product_id: int) -> tuple[Product, list[str], str]:
    """Draft a name + description for one product from its stored cover image.

    Returns (product, suggested_tags, language_note). The agent's tags and
    language note are display hints — we persist only name + description
    (the fields the Product model has). Price/stock are untouched: the agent
    literally cannot set them (its schema has no such field — CONCEPTS §4).
    """
    product = db.get(Product, product_id)
    if product is None:
        raise ProductError(f"Product {product_id} not found.")

    # Read OUR stored cover bytes (never a live TikTok URL — expired by now).
    cover_bytes = _read_cover_bytes(product)
    if cover_bytes is None:
        raise ProductError("This product has no stored cover image to draft from.")

    result = draft_agent.draft_from_video(  # may raise DraftError
        cover_bytes=cover_bytes,
        caption=product.caption,
        hashtags=[h.get("name", "") for h in product.hashtags],
    )

    # The agent PROPOSES; we write only the descriptive fields.
    product.name = result.name
    product.description = result.description
    db.commit()
    db.refresh(product)
    return product, result.tags, result.language_note


def _read_cover_bytes(product: Product) -> bytes | None:
    """Load the on-disk cover we stored at ingest. Isolated so the S3 swap
    later is one function, and so tests can monkeypatch it."""
    if not product.cover_url:
        return None
    from app.services.scraper import MEDIA_DIR

    # cover_url is stored as "covers/<id>.jpg" (relative to the media root).
    path = MEDIA_DIR.parent / product.cover_url
    return path.read_bytes() if path.exists() else None


# ── Update: seller confirms — set words, set money, maybe publish ─────────────
def update_product(db: Session, product_id: int, changes: ProductUpdateIn) -> Product:
    """Apply a seller's edits. This is the DETERMINISTIC money path — the only
    place price/stock/status change, driven by the human, tested to the hilt."""
    product = db.get(Product, product_id)
    if product is None:
        raise ProductError(f"Product {product_id} not found.")

    if changes.name is not None:
        product.name = changes.name
    if changes.description is not None:
        product.description = changes.description
    if changes.price_kes is not None:
        product.price_kes = changes.price_kes
    if changes.stock is not None:
        product.stock = changes.stock

    if changes.publish:
        # The rule, enforced here with a friendly message AND by the DB
        # CheckConstraint ck_products_published_needs_price as the backstop.
        price = product.price_kes
        if price is None:
            raise ProductError("Cannot publish without a price — set price_kes first.")
        product.status = ProductStatus.PUBLISHED

    db.commit()
    db.refresh(product)
    return product


# ── Public page: seller + their live, available products ──────────────────────
def get_public_page(db: Session, handle: str) -> Seller:
    """Load a seller by public handle for bob.link/<handle>.

    Returns the Seller; the caller reads seller.products and filters to
    published+available for the public shape. Raises ProductError (→ 404) when
    the handle is unknown — we never leak whether a handle 'exists but is empty'
    vs 'never existed' beyond a plain not-found."""
    seller = db.scalar(select(Seller).where(Seller.handle == handle))
    if seller is None:
        raise ProductError(f"No shop at /{handle}.")
    return seller


def public_products(seller: Seller) -> list[Product]:
    """The buyer-visible subset: published AND in stock. Sold-out published
    items still show (as SOLD) so buyers see the drop; drafts never show."""
    return [p for p in seller.products if p.status == ProductStatus.PUBLISHED]
