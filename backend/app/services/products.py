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
from app.models.account import Account
from app.models.product import Product, ProductStatus
from app.models.seller import Seller
from app.schemas.product import ProductUpdateIn


class ProductError(Exception):
    """A business-rule failure (not a 500). Routes map it to a 4xx with this
    message — safe to show a human."""


# ── Ownership (the account-scoping boundary) ──────────────────────────────────
def list_account_products(db: Session, account: Account) -> list[Product]:
    """Every product belonging to the account's storefront (drafts + published),
    newest first — what the dashboard loads on open. Empty if not connected."""
    seller = db.scalar(select(Seller).where(Seller.account_id == account.id))
    if seller is None:
        return []
    return sorted(seller.products, key=lambda p: p.created_at, reverse=True)


def _owned_product(db: Session, account: Account, product_id: int) -> Product:
    """Fetch a product ONLY if it belongs to this account's storefront.
    A product the caller doesn't own reads exactly like one that doesn't exist
    (same not-found) — we never reveal other sellers' product ids."""
    product = db.get(Product, product_id)
    if product is None or product.seller is None or product.seller.account_id != account.id:
        raise ProductError(f"Product {product_id} not found.")
    return product


# ── Autofill: run the vision draft agent on ONE product (the 🤖 step) ─────────
def autofill_product(
    db: Session, account: Account, product_id: int
) -> tuple[Product, "draft_agent.ProductDraft"]:
    """Draft one product from its stored cover image.

    Returns (product, draft). We persist ONLY name + description onto the
    product. The draft's suggested_price_kes is passed back to the caller as a
    SUGGESTION (it pre-fills the seller's price box) but is NEVER written to
    product.price_kes here — the seller's PATCH remains the only writer of the
    stored price (CONCEPTS §4). Stock is likewise untouched.
    """
    product = _owned_product(db, account, product_id)

    # Read OUR stored cover bytes (never a live TikTok URL — expired by now).
    cover_bytes = _read_cover_bytes(product)
    if cover_bytes is None:
        raise ProductError("This product has no stored cover image to draft from.")

    draft = _draft_product(product, cover_bytes)  # cover + video-price fallback; may raise DraftError
    db.commit()
    db.refresh(product)
    return product, draft


def _apply_draft(product: Product, draft: "draft_agent.ProductDraft") -> None:
    """Write an agent draft onto a product. Name/description are the agent's to
    fill. The AI-read price is written as a DRAFT price (price_kes) ONLY when the
    seller hasn't set one — but the product stays DRAFT. Going LIVE still needs
    the seller's explicit Publish (the human gate). So the AI removes typing, it
    never sells anything at an unconfirmed price. See CONCEPTS §4."""
    product.name = draft.name
    product.description = draft.description
    if product.price_kes is None and draft.suggested_price_kes is not None:
        product.price_kes = draft.suggested_price_kes


def _draft_product(product: Product, cover_bytes: bytes) -> "draft_agent.ProductDraft":
    """Cover-first draft, then the VIDEO fallback for a price the cover didn't show.

    1. Draft from the cover (name/description + a printed price if visible).
    2. If NO price landed AND we have the video, watch/listen for one — the
       cover-first, video-fallback rule (we only spend a video call when needed).
    The video price is a DRAFT price like any other; publish stays the human gate.
    Raises DraftError/DraftQuotaError from the cover pass; the video step never
    raises (best-effort)."""
    draft = draft_agent.draft_from_video(
        cover_bytes=cover_bytes,
        caption=product.caption,
        hashtags=[h.get("name", "") for h in product.hashtags],
    )
    _apply_draft(product, draft)  # sets name/desc + a cover price if there was one

    if product.price_kes is None and product.video_download_url:
        from app.services import scraper

        video_bytes = scraper.download_video_bytes(product.video_download_url)
        price = draft_agent.read_price_from_video(video_bytes, product_name=product.name)
        if price is not None:
            product.price_kes = price

    return draft


def autodraft_account(db: Session, account: Account) -> tuple[list[Product], bool]:
    """Auto-draft EVERY un-drafted product for the account — the seller does no
    clicking; the shop fills itself. Best-effort: images that fail are skipped;
    the AI usage cap STOPS the batch (returns ai_paused=True) so we never hammer
    a dead quota. Idempotent — already-drafted products are left untouched."""
    seller = db.scalar(select(Seller).where(Seller.account_id == account.id))
    if seller is None:
        return [], False

    ai_paused = False
    for product in list(seller.products):
        if product.name.strip():
            continue  # already drafted — skip (idempotent + cost-bounded)
        cover = _read_cover_bytes(product)
        if cover is None:
            continue  # no image to read; leave for the seller
        try:
            _draft_product(product, cover)  # cover + video-price fallback
        except draft_agent.DraftQuotaError:
            ai_paused = True
            break  # stop — the daily cap is hit; don't burn the rest failing
        except draft_agent.DraftError:
            continue  # one unreadable image shouldn't sink the whole batch
        db.commit()  # per-product → partial progress survives a later quota stop

    return list_account_products(db, account), ai_paused


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
def update_product(
    db: Session, account: Account, product_id: int, changes: ProductUpdateIn
) -> Product:
    """Apply a seller's edits to THEIR OWN product. This is the DETERMINISTIC
    money path — the only place price/stock/status change, driven by the human,
    scoped to the owner, tested to the hilt."""
    product = _owned_product(db, account, product_id)

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
    """Load a seller by public handle for sokolink/<handle>.

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
