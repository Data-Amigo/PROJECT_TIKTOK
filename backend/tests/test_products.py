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
def test_autofill_drafts_and_persists_draft_price(client, db_session, monkeypatch):
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
    # The AI-read price is now persisted as a DRAFT price (removes typing)...
    assert body["product"]["price_kes"] == 600
    # ...but the product is NOT live — publish is still the human gate.
    assert body["product"]["status"] == "draft"


def test_autofill_does_not_clobber_a_seller_set_price(client, db_session, monkeypatch):
    me = _account(db_session)
    p = _product(db_session, _seller(db_session, me), vid="502", price=999)  # seller already priced it
    p.cover_url = "covers/502.jpg"
    db_session.flush()
    fake = draft_mod.ProductDraft(
        is_product=True, name="X", description="", tags=[], suggested_price_kes=600, language_note="",
    )
    monkeypatch.setattr(svc, "_read_cover_bytes", lambda product: b"img")
    monkeypatch.setattr(draft_mod, "draft_from_video", lambda **kw: fake)
    body = client.post(f"/api/products/{p.id}/autofill", headers=_auth(me)).json()
    assert body["product"]["price_kes"] == 999   # seller's price wins


def test_video_fallback_fills_price_the_cover_missed(client, db_session, monkeypatch):
    """Cover shows no price → watch the video for one, and persist it as a draft price."""
    me = _account(db_session)
    p = _product(db_session, _seller(db_session, me), vid="530")
    p.cover_url = "covers/530.jpg"
    p.video_download_url = "https://api.apify.com/v2/key-value-stores/x/records/v.mp4"
    db_session.flush()

    cover_draft = draft_mod.ProductDraft(  # cover found NO price
        is_product=True, name="Ripped Jeans", description="Ripped Jeans", tags=[], suggested_price_kes=None,
    )
    monkeypatch.setattr(svc, "_read_cover_bytes", lambda product: b"img")
    monkeypatch.setattr(draft_mod, "draft_from_video", lambda **kw: cover_draft)
    monkeypatch.setattr("app.services.scraper.download_video_bytes", lambda url: b"vid")
    monkeypatch.setattr(draft_mod, "read_price_from_video", lambda vb, product_name="": 750)  # video heard "750"

    body = client.post(f"/api/products/{p.id}/autofill", headers=_auth(me)).json()
    assert body["product"]["price_kes"] == 750       # price came from the video
    assert body["product"]["status"] == "draft"      # still the human gate


def test_video_fallback_skipped_when_cover_has_a_price(client, db_session, monkeypatch):
    """Cover already gave a price → never spend a video call (the cost rail)."""
    me = _account(db_session)
    p = _product(db_session, _seller(db_session, me), vid="531")
    p.cover_url = "covers/531.jpg"
    p.video_download_url = "https://api.apify.com/v2/key-value-stores/x/records/v.mp4"
    db_session.flush()

    def _must_not_run(*a, **k):
        raise AssertionError("video path must not run when the cover has a price")

    cover_draft = draft_mod.ProductDraft(
        is_product=True, name="Jeans", description="Jeans", tags=[], suggested_price_kes=600,
    )
    monkeypatch.setattr(svc, "_read_cover_bytes", lambda product: b"img")
    monkeypatch.setattr(draft_mod, "draft_from_video", lambda **kw: cover_draft)
    monkeypatch.setattr("app.services.scraper.download_video_bytes", _must_not_run)
    monkeypatch.setattr(draft_mod, "read_price_from_video", _must_not_run)

    body = client.post(f"/api/products/{p.id}/autofill", headers=_auth(me)).json()
    assert body["product"]["price_kes"] == 600       # from the cover; no video touched


def test_autodraft_drafts_all_undrafted(client, db_session, monkeypatch):
    me = _account(db_session)
    s = _seller(db_session, me, handle="autoshop")
    a = _product(db_session, s, vid="510"); a.cover_url = "covers/510.jpg"
    b = _product(db_session, s, vid="511"); b.cover_url = "covers/511.jpg"
    done = _product(db_session, s, vid="512", name="Already named"); done.cover_url = "covers/512.jpg"
    db_session.flush()

    fake = draft_mod.ProductDraft(
        is_product=True, name="AI Drafted", description="d", tags=[], suggested_price_kes=700, language_note="",
    )
    monkeypatch.setattr(svc, "_read_cover_bytes", lambda product: b"img")
    monkeypatch.setattr(draft_mod, "draft_from_video", lambda **kw: fake)

    body = client.post("/api/products/autodraft", headers=_auth(me)).json()
    assert body["ai_paused"] is False
    by_vid = {p["tiktok_video_id"]: p for p in body["products"]}
    assert by_vid["510"]["name"] == "AI Drafted" and by_vid["510"]["price_kes"] == 700
    assert by_vid["511"]["name"] == "AI Drafted"
    assert by_vid["512"]["name"] == "Already named"   # left untouched (idempotent)


def test_autodraft_pauses_on_quota(client, db_session, monkeypatch):
    me = _account(db_session)
    s = _seller(db_session, me, handle="quotashop2")
    p = _product(db_session, s, vid="520"); p.cover_url = "covers/520.jpg"
    db_session.flush()

    def _quota(**kw):
        raise draft_mod.DraftQuotaError("limit reached")

    monkeypatch.setattr(svc, "_read_cover_bytes", lambda product: b"img")
    monkeypatch.setattr(draft_mod, "draft_from_video", _quota)

    body = client.post("/api/products/autodraft", headers=_auth(me)).json()
    assert body["ai_paused"] is True
    assert body["products"][0]["name"] == ""   # left un-drafted for manual fallback


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


# ── Sales chat (agent mocked) ─────────────────────────────────────────────────
def test_shop_chat_answers(client, db_session, monkeypatch):
    from app.agent import sales

    me = _account(db_session)
    s = _seller(db_session, me, handle="chatshop")
    _product(db_session, s, vid="800", status=ProductStatus.PUBLISHED, price=500, stock=3, name="Blue Dress")
    db_session.commit()

    captured = {}

    def _fake_answer(shop_name, catalogue, history, featured=None):
        captured["catalogue"] = catalogue
        return sales.SalesReply(reply="We have a Blue Dress for KES 500!")

    monkeypatch.setattr(sales, "answer", _fake_answer)
    r = client.post("/api/pages/chatshop/chat", json={"messages": [{"role": "user", "content": "got dresses?"}]})
    assert r.status_code == 200
    assert "Blue Dress" in r.json()["reply"]
    assert r.json()["customer_captured"] is False   # nothing to capture here
    # the agent was grounded in the real catalogue
    assert any(item.name == "Blue Dress" and item.price_kes == 500 for item in captured["catalogue"])


def test_shop_chat_captures_name_and_phone_as_a_customer(client, db_session, monkeypatch):
    from sqlalchemy import select

    from app.agent import sales
    from app.models.customer import Customer

    me = _account(db_session)
    s = _seller(db_session, me, handle="leadshop")
    db_session.commit()

    # The bot reports it heard a name + phone this turn.
    def _fake_answer(shop_name, catalogue, history, featured=None):
        return sales.SalesReply(
            reply="Asante Aisha! Nakutumia request ya M-Pesa saa hii 😊",
            customer_name="Aisha", customer_phone="0712345678", wants_to_buy=True,
        )

    monkeypatch.setattr(sales, "answer", _fake_answer)
    r = client.post("/api/pages/leadshop/chat", json={"messages": [{"role": "user", "content": "nataka hii, Aisha 0712345678"}]})
    assert r.status_code == 200
    assert r.json()["customer_captured"] is True

    cust = db_session.scalar(select(Customer).where(Customer.seller_id == s.id))
    assert cust is not None
    assert cust.name == "Aisha"
    assert cust.phone == "254712345678"   # normalized at the border


def test_shop_chat_rejects_non_user_first_message(client, db_session):
    me = _account(db_session)
    _seller(db_session, me, handle="chatshop2")
    db_session.commit()
    r = client.post("/api/pages/chatshop2/chat", json={"messages": [{"role": "assistant", "content": "hi"}]})
    assert r.status_code == 400


def test_shop_chat_unknown_shop_is_404(client):
    r = client.post("/api/pages/nobody/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 404


def test_resolve_video_matches_a_pasted_link_to_a_product(client, db_session):
    me = _account(db_session)
    s = _seller(db_session, me, handle="pasteshop")
    vid = "9900000000000000123"  # synthetic — the real ids live in the shared DB
    _product(db_session, s, vid=vid, status=ProductStatus.PUBLISHED,
             price=600, stock=2, name="Ripped Jeans")
    db_session.commit()

    r = client.post(
        "/api/pages/pasteshop/resolve-video",
        json={"url": f"https://www.tiktok.com/@classycloset/video/{vid}?is_from_webapp=1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["video_id"] == vid
    assert body["product"]["name"] == "Ripped Jeans"


def test_resolve_video_unmatched_link_returns_null_product(client, db_session):
    me = _account(db_session)
    _seller(db_session, me, handle="pasteshop2")
    db_session.commit()
    # A well-formed TikTok link, but no product on that video in THIS shop.
    r = client.post(
        "/api/pages/pasteshop2/resolve-video",
        json={"url": "https://www.tiktok.com/@someoneelse/video/1111111111111111111"},
    )
    assert r.status_code == 200
    assert r.json()["product"] is None


def test_system_prompt_grounds_and_guards():
    """The prompt (where the conversational intelligence lives) must: inject the
    live catalogue as the source of truth, decode Sheng, forbid inventing
    colours/sizes, and forbid formal textbook Swahili. No model call — this
    asserts the guardrail text itself, deterministically."""
    from app.agent import sales

    catalogue = [
        sales.CatalogueItem(name="Ripped Jeans", price_kes=600, available=False, description="denim"),
        sales.CatalogueItem(name="Ladies Jeans", price_kes=550, available=True, description="slim fit"),
    ]
    prompt = sales._system_prompt("Classy Closet", catalogue, featured=None)

    # Source of truth: the real catalogue (name + price + stock state) is injected.
    assert "Ripped Jeans" in prompt and "KES 600" in prompt and "SOLD OUT" in prompt
    assert "Ladies Jeans" in prompt and "in stock" in prompt
    # Comprehension: it teaches the model to decode Sheng intent.
    assert "nadai" in prompt and "bei?" in prompt
    # Honesty rail: never invent a colour/size, never pitch sold-out stock.
    assert "you do NOT track colours or sizes" in prompt
    assert "SOLD OUT = cannot be bought now" in prompt
    # Voice rail: no formal textbook Swahili; mirror the customer.
    assert "textbook Swahili" in prompt
