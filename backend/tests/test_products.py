"""
Products + Pages API tests.

Two kinds here:
  * MONEY PATH (patch/publish, public page) — tested against real Postgres via
    the rolled-back db_session, NO external calls. These are the ones that must
    never break, so they exercise the real DB constraints.
  * ORCHESTRATION (ingest, autofill) — the scraper and vision agent are
    monkeypatched out (no network, no cost); we test that OUR wiring creates the
    right rows idempotently and that the agent's output lands only in the
    word fields, never money.
"""

import pytest

from app.models.product import Product, ProductStatus
from app.models.seller import Seller
from app.services import products as svc
from app.services import scraper as scraper_mod
from app.agent import draft as draft_mod


# ── Helpers ───────────────────────────────────────────────────────────────────
def _make_seller(db, handle="mama_wanjiku") -> Seller:
    s = Seller(handle=handle, display_name="Mama Wanjiku", tiktok_username=handle)
    db.add(s)
    db.flush()
    return s


def _make_product(db, seller, *, vid, status=ProductStatus.DRAFT, price=None, stock=0, name="") -> Product:
    p = Product(
        tiktok_video_id=vid,
        seller_id=seller.id,
        video_url=f"https://tiktok.com/@x/video/{vid}",
        name=name,
        price_kes=price,
        stock=stock,
        status=status,
    )
    db.add(p)
    db.flush()
    return p


# ── PATCH: the deterministic money path ───────────────────────────────────────
def test_patch_sets_price_and_stock(client, db_session):
    seller = _make_seller(db_session)
    p = _make_product(db_session, seller, vid="1001")

    r = client.patch(f"/api/products/{p.id}", json={"price_kes": 800, "stock": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["price_kes"] == 800
    assert body["stock"] == 5
    assert body["status"] == "draft"          # setting price alone doesn't publish
    assert body["is_available"] is False       # not published yet


def test_publish_requires_a_price(client, db_session):
    seller = _make_seller(db_session)
    p = _make_product(db_session, seller, vid="1002")   # no price

    r = client.patch(f"/api/products/{p.id}", json={"publish": True})
    assert r.status_code == 400
    assert "price" in r.json()["detail"].lower()


def test_publish_with_price_goes_live_and_available(client, db_session):
    seller = _make_seller(db_session)
    p = _make_product(db_session, seller, vid="1003")

    r = client.patch(f"/api/products/{p.id}", json={"price_kes": 1200, "stock": 3, "publish": True})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "published"
    assert body["is_available"] is True        # published + stock > 0


def test_patch_rejects_zero_price_at_the_border(client, db_session):
    """price_kes must be > 0 (pydantic gt=0) — caught before the DB."""
    seller = _make_seller(db_session)
    p = _make_product(db_session, seller, vid="1004")
    r = client.patch(f"/api/products/{p.id}", json={"price_kes": 0})
    assert r.status_code == 422                 # pydantic validation error


# ── Public page: buyers see only the right things ─────────────────────────────
def test_public_page_shows_published_hides_drafts(client, db_session):
    seller = _make_seller(db_session, handle="kinjo")
    _make_product(db_session, seller, vid="2001", status=ProductStatus.PUBLISHED, price=500, stock=4, name="Duvet")
    _make_product(db_session, seller, vid="2002", status=ProductStatus.PUBLISHED, price=900, stock=0, name="Sold Carpet")
    _make_product(db_session, seller, vid="2003", status=ProductStatus.DRAFT, name="Secret draft")
    db_session.commit()

    r = client.get("/api/pages/kinjo")
    assert r.status_code == 200
    body = r.json()
    assert body["handle"] == "kinjo"
    names = {p["name"]: p for p in body["products"]}
    assert "Secret draft" not in names          # drafts never public
    assert names["Duvet"]["is_available"] is True
    assert names["Sold Carpet"]["is_available"] is False   # sold-out shows as SOLD
    # The public shape must not leak internal fields:
    assert "tiktok_video_id" not in names["Duvet"]
    assert "status" not in names["Duvet"]


def test_public_page_unknown_handle_is_404(client):
    r = client.get("/api/pages/nobody_here_at_all")
    assert r.status_code == 404


# ── Ingest: orchestration, scraper mocked out ─────────────────────────────────
def _fake_videos(handle):
    """Two fake scraped videos shaped like the real TikTokVideo schema."""
    return [
        scraper_mod.TikTokVideo(
            id="3001",
            text="#duvets",
            webVideoUrl="https://tiktok.com/@x/video/3001",
            authorMeta={"name": handle, "nickName": "Shop X", "signature": "Nairobi 0700000000"},
            videoMeta={"coverUrl": "https://cdn/expiring.jpg", "duration": 30},
            hashtags=[{"name": "duvets"}],
        ),
        scraper_mod.TikTokVideo(
            id="3002",
            text="#carpet",
            webVideoUrl="https://tiktok.com/@x/video/3002",
            authorMeta={"name": handle, "nickName": "Shop X", "signature": "Nairobi 0700000000"},
            videoMeta={"coverUrl": None, "duration": 20},
            hashtags=[{"name": "carpet"}],
        ),
    ]


def test_ingest_creates_drafts_and_is_idempotent(client, db_session, monkeypatch):
    monkeypatch.setattr(scraper_mod, "fetch_profile", lambda h, limit=6: _fake_videos("shopx"))
    monkeypatch.setattr(scraper_mod, "save_cover", lambda v: None)  # skip real download

    r1 = client.post("/api/products/ingest", json={"handle": "shopx"})
    assert r1.status_code == 201
    first = r1.json()
    assert len(first) == 2
    assert all(p["status"] == "draft" for p in first)      # ingest never publishes
    assert all(p["price_kes"] is None for p in first)      # ingest never sets money

    # A seller row was created from the scraped author.
    assert db_session.scalar(
        Seller.__table__.select().where(Seller.tiktok_username == "shopx")
    ) is not None

    # Ingest again → SAME two rows refreshed, not duplicated (idempotent by video id).
    r2 = client.post("/api/products/ingest", json={"handle": "shopx"})
    assert r2.status_code == 201
    ids1 = {p["id"] for p in first}
    ids2 = {p["id"] for p in r2.json()}
    assert ids1 == ids2


# ── Autofill: the agent fills WORDS only, never money ─────────────────────────
def test_autofill_sets_name_and_description_only(client, db_session, monkeypatch):
    seller = _make_seller(db_session, handle="autofillshop")
    p = _make_product(db_session, seller, vid="4001", price=None, stock=0)
    p.cover_url = "covers/4001.jpg"
    db_session.flush()

    fake_draft = draft_mod.ProductDraft(
        is_product=True,
        name="Fluffy Duvet Set",
        description="A soft grey duvet set.",
        tags=["duvet", "bedding"],
        suggested_price_kes=600,   # agent read "600 ksh" off the image
        language_note="",
    )
    monkeypatch.setattr(svc, "_read_cover_bytes", lambda product: b"fake-image-bytes")
    monkeypatch.setattr(draft_mod, "draft_from_video", lambda **kw: fake_draft)

    r = client.post(f"/api/products/{p.id}/autofill")
    assert r.status_code == 200
    body = r.json()
    assert body["product"]["name"] == "Fluffy Duvet Set"
    assert body["product"]["description"] == "A soft grey duvet set."
    assert body["suggested_tags"] == ["duvet", "bedding"]
    assert body["is_product"] is True
    # The price SUGGESTION rides back for the UI to pre-fill...
    assert body["suggested_price_kes"] == 600
    # ...but the GUARDRAIL holds: it was NOT written to the stored product.
    # Only the seller's PATCH can do that.
    assert body["product"]["price_kes"] is None
    assert body["product"]["stock"] == 0
    assert body["product"]["status"] == "draft"


def test_autofill_flags_non_product(client, db_session, monkeypatch):
    """A reply/skit video comes back is_product=False so the inbox can flag it."""
    seller = _make_seller(db_session, handle="skitshop")
    p = _make_product(db_session, seller, vid="4002")
    p.cover_url = "covers/4002.jpg"
    db_session.flush()

    fake_draft = draft_mod.ProductDraft(
        is_product=False,
        not_product_reason="reply video, no product shown",
        name="Unclear — needs seller review",
        description="",
        tags=[],
        suggested_price_kes=None,
        language_note="",
    )
    monkeypatch.setattr(svc, "_read_cover_bytes", lambda product: b"x")
    monkeypatch.setattr(draft_mod, "draft_from_video", lambda **kw: fake_draft)

    body = client.post(f"/api/products/{p.id}/autofill").json()
    assert body["is_product"] is False
    assert "reply" in body["not_product_reason"]
    assert body["suggested_price_kes"] is None


def test_autofill_missing_product_is_404(client, monkeypatch):
    monkeypatch.setattr(svc, "_read_cover_bytes", lambda product: b"x")
    r = client.post("/api/products/999999/autofill")
    assert r.status_code == 404
