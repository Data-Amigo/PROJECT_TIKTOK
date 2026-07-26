"""
Products API tests — now ACCOUNT-SCOPED.

Every /api/products/* route requires login and only touches the caller's own
products. So these tests create an account, a token, a storefront (seller), and
products under it — then exercise the money path, ownership, and /mine.
Orchestration (autofill agent, refresh scrape) is mocked: no network, no cost.
"""

import itertools

from app.agent import draft as draft_mod
from app.models.account import Account
from app.models.product import Product, ProductStatus
from app.models.seller import Seller
from app.security import create_access_token, hash_password
from app.services import products as svc
from app.services import scraper as scraper_mod

_seq = itertools.count(1)  # unique emails/phones/handles across the session


# ── Fixtures / helpers ────────────────────────────────────────────────────────
def _account(db) -> Account:
    i = next(_seq)
    a = Account(
        name=f"Seller {i}",
        email=f"seller{i}@example.com",
        phone=f"2547{i:08d}",
        password_hash=hash_password("password8"),
    )
    db.add(a)
    db.flush()
    return a


def _auth(account: Account) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(account.id))}"}


def _seller(db, account: Account, handle: str | None = None) -> Seller:
    s = Seller(
        account_id=account.id,
        handle=handle or f"shop{next(_seq)}",
        display_name="My Shop",
        tiktok_username=handle or f"tt{next(_seq)}",
    )
    db.add(s)
    db.flush()
    return s


def _product(db, seller, *, vid, status=ProductStatus.DRAFT, price=None, stock=0, name="") -> Product:
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


# ── Auth is required ──────────────────────────────────────────────────────────
def test_product_routes_require_login(client):
    assert client.get("/api/products/mine").status_code == 401
    assert client.post("/api/products/1/autofill").status_code == 401
    assert client.patch("/api/products/1", json={"price_kes": 100}).status_code == 401


# ── /mine ─────────────────────────────────────────────────────────────────────
def test_mine_returns_only_my_products(client, db_session):
    me = _account(db_session)
    my_seller = _seller(db_session, me, handle="mine")
    _product(db_session, my_seller, vid="100", name="Mine A")
    _product(db_session, my_seller, vid="101", name="Mine B")
    # someone else's product must not appear
    other = _account(db_session)
    other_seller = _seller(db_session, other, handle="other")
    _product(db_session, other_seller, vid="200", name="Not mine")
    db_session.commit()

    r = client.get("/api/products/mine", headers=_auth(me))
    assert r.status_code == 200
    names = {p["name"] for p in r.json()}
    assert names == {"Mine A", "Mine B"}


# ── Money path (PATCH) ────────────────────────────────────────────────────────
def test_patch_sets_price_and_stock(client, db_session):
    me = _account(db_session)
    p = _product(db_session, _seller(db_session, me), vid="300")
    r = client.patch(f"/api/products/{p.id}", json={"price_kes": 800, "stock": 5}, headers=_auth(me))
    assert r.status_code == 200
    body = r.json()
    assert body["price_kes"] == 800 and body["stock"] == 5
    assert body["status"] == "draft" and body["is_available"] is False


def test_publish_requires_a_price(client, db_session):
    me = _account(db_session)
    p = _product(db_session, _seller(db_session, me), vid="301")
    r = client.patch(f"/api/products/{p.id}", json={"publish": True}, headers=_auth(me))
    assert r.status_code == 400
    assert "price" in r.json()["detail"].lower()


def test_publish_with_price_goes_live(client, db_session):
    me = _account(db_session)
    p = _product(db_session, _seller(db_session, me), vid="302")
    r = client.patch(f"/api/products/{p.id}", json={"price_kes": 1200, "stock": 3, "publish": True}, headers=_auth(me))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "published" and body["is_available"] is True


def test_patch_rejects_zero_price(client, db_session):
    me = _account(db_session)
    p = _product(db_session, _seller(db_session, me), vid="303")
    r = client.patch(f"/api/products/{p.id}", json={"price_kes": 0}, headers=_auth(me))
    assert r.status_code == 422


# ── Ownership: you can't touch another seller's products ──────────────────────
def test_cannot_patch_another_sellers_product(client, db_session):
    owner = _account(db_session)
    p = _product(db_session, _seller(db_session, owner, handle="owner"), vid="400", price=100)
    attacker = _account(db_session)
    r = client.patch(f"/api/products/{p.id}", json={"price_kes": 1}, headers=_auth(attacker))
    assert r.status_code == 400   # ProductError → not found, mapped to 400 (no leak)


def test_cannot_autofill_another_sellers_product(client, db_session):
    owner = _account(db_session)
    p = _product(db_session, _seller(db_session, owner, handle="owner2"), vid="401")
    attacker = _account(db_session)
    r = client.post(f"/api/products/{p.id}/autofill", headers=_auth(attacker))
    assert r.status_code == 404


# ── Autofill (agent mocked) ───────────────────────────────────────────────────
def test_autofill_sets_words_suggests_price_never_persists_it(client, db_session, monkeypatch):
    me = _account(db_session)
    p = _product(db_session, _seller(db_session, me), vid="500")
    p.cover_url = "covers/500.jpg"
    db_session.flush()

    fake = draft_mod.ProductDraft(
        is_product=True, name="Fluffy Duvet", description="Soft grey duvet.",
        tags=["duvet"], suggested_price_kes=600, language_note="",
    )
    monkeypatch.setattr(svc, "_read_cover_bytes", lambda product: b"img")
    monkeypatch.setattr(draft_mod, "draft_from_video", lambda **kw: fake)

    body = client.post(f"/api/products/{p.id}/autofill", headers=_auth(me)).json()
    assert body["product"]["name"] == "Fluffy Duvet"
    assert body["suggested_price_kes"] == 600
    assert body["product"]["price_kes"] is None   # guardrail: not persisted


def test_autofill_quota_returns_429(client, db_session, monkeypatch):
    me = _account(db_session)
    p = _product(db_session, _seller(db_session, me), vid="501")

    def _quota(db, account, pid):
        raise draft_mod.DraftQuotaError("The image reader has reached today's usage limit.")

    monkeypatch.setattr(svc, "autofill_product", _quota)
    r = client.post(f"/api/products/{p.id}/autofill", headers=_auth(me))
    assert r.status_code == 429


# ── Refresh (scraper mocked) ──────────────────────────────────────────────────
def test_refresh_pulls_videos_into_products(client, db_session, monkeypatch):
    me = _account(db_session)
    seller = _seller(db_session, me, handle="refreshshop")
    seller.tiktok_username = "refreshshop"
    db_session.flush()

    def _fake_videos(username, limit=8):
        return [
            scraper_mod.TikTokVideo(
                id="600", text="#x", webVideoUrl="https://tiktok.com/@x/video/600",
                authorMeta={"name": "refreshshop", "nickName": "Refresh Shop", "signature": "", "fans": 10},
                videoMeta={"coverUrl": None, "duration": 5}, hashtags=[],
            )
        ]

    monkeypatch.setattr(scraper_mod, "fetch_profile", _fake_videos)
    monkeypatch.setattr(scraper_mod, "save_cover", lambda v: None)
    monkeypatch.setattr(scraper_mod, "save_avatar", lambda u, url: None)

    r = client.post("/api/products/refresh", headers=_auth(me))
    assert r.status_code == 200
    assert any(p["tiktok_video_id"] == "600" for p in r.json())


# ── Public page (no auth) ─────────────────────────────────────────────────────
def test_public_page_shows_published_hides_drafts(client, db_session):
    me = _account(db_session)
    seller = _seller(db_session, me, handle="kinjo")
    _product(db_session, seller, vid="700", status=ProductStatus.PUBLISHED, price=500, stock=4, name="Duvet")
    _product(db_session, seller, vid="701", status=ProductStatus.PUBLISHED, price=900, stock=0, name="Sold Carpet")
    _product(db_session, seller, vid="702", status=ProductStatus.DRAFT, name="Secret draft")
    db_session.commit()

    body = client.get("/api/pages/kinjo").json()
    names = {p["name"]: p for p in body["products"]}
    assert "Secret draft" not in names
    assert names["Duvet"]["is_available"] is True
    assert names["Sold Carpet"]["is_available"] is False
    assert "status" not in names["Duvet"]   # public shape doesn't leak internals


def test_public_page_unknown_handle_is_404(client):
    assert client.get("/api/pages/nobody_here").status_code == 404
