"""Storefront (connect TikTok) tests — scraper mocked, no network."""

import itertools

from app.agent import draft as draft_mod  # noqa: F401  (kept parallel to other suites)
from app.models.account import Account
from app.security import create_access_token, hash_password
from app.services import scraper as scraper_mod
from app.services import storefront as store_mod

_seq = itertools.count(1)


def _account(db) -> Account:
    i = next(_seq)
    a = Account(
        name=f"Seller {i}", email=f"acc{i}@example.com",
        phone=f"2547{i:08d}", password_hash=hash_password("password8"),
    )
    db.add(a)
    db.flush()
    return a


def _auth(a: Account) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(a.id))}"}


def _fake_profile(username, limit=8):
    return [
        scraper_mod.TikTokVideo(
            id="900", text="#duvets", webVideoUrl="https://tiktok.com/@x/video/900",
            authorMeta={"name": username, "nickName": "Shop X", "signature": "Nairobi 0700000000", "fans": 1400000, "avatar": "https://cdn/a.jpg"},
            videoMeta={"coverUrl": None, "duration": 20}, hashtags=[{"name": "duvets"}],
        ),
        scraper_mod.TikTokVideo(
            id="901", text="#carpet", webVideoUrl="https://tiktok.com/@x/video/901",
            authorMeta={"name": username, "nickName": "Shop X", "signature": "", "fans": 1400000, "avatar": "https://cdn/a.jpg"},
            videoMeta={"coverUrl": None, "duration": 10}, hashtags=[],
        ),
    ]


def _mock_scraper(monkeypatch):
    monkeypatch.setattr(scraper_mod, "fetch_profile", _fake_profile)
    monkeypatch.setattr(scraper_mod, "save_cover", lambda v: None)
    monkeypatch.setattr(scraper_mod, "save_avatar", lambda u, url: None)


def test_connect_requires_login(client):
    assert client.post("/api/account/connect-tiktok", json={"username": "shopx"}).status_code == 401


def test_storefront_is_null_before_connecting(client, db_session):
    me = _account(db_session)
    r = client.get("/api/account/storefront", headers=_auth(me))
    assert r.status_code == 200
    assert r.json() is None


def test_connect_creates_storefront_and_products(client, db_session, monkeypatch):
    _mock_scraper(monkeypatch)
    me = _account(db_session)

    r = client.post("/api/account/connect-tiktok", json={"username": "@shopx"}, headers=_auth(me))
    assert r.status_code == 200
    shop = r.json()
    assert shop["tiktok_username"] == "shopx"
    assert shop["display_name"] == "Shop X"
    assert shop["follower_count"] == 1400000
    assert shop["handle"] == "shopx"
    assert shop["phone"] == me.phone           # M-Pesa number carried from the account

    # storefront now returns it, and its videos landed as products
    assert client.get("/api/account/storefront", headers=_auth(me)).json()["handle"] == "shopx"
    mine = client.get("/api/products/mine", headers=_auth(me)).json()
    assert {p["tiktok_video_id"] for p in mine} == {"900", "901"}
    assert all(p["status"] == "draft" for p in mine)


def test_connect_conflicts_when_username_owned_by_another(client, db_session, monkeypatch):
    _mock_scraper(monkeypatch)
    a = _account(db_session)
    client.post("/api/account/connect-tiktok", json={"username": "sharedname"}, headers=_auth(a))
    b = _account(db_session)
    r = client.post("/api/account/connect-tiktok", json={"username": "sharedname"}, headers=_auth(b))
    assert r.status_code == 409
