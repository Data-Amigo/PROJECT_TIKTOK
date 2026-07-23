"""
Scraper service tests — the validation border, exercised WITHOUT the network.

Philosophy: we don't test Apify (their job) or httpx (its job); we test OUR
border: does real-shaped data parse, does garbage get rejected, do seller
inputs normalize. The fixture below is a trimmed REAL item from spike 00 —
tests against invented data prove nothing about production payloads.
"""

import pytest
from pydantic import ValidationError

from app.services.scraper import TikTokVideo, normalize_username

# Trimmed from spike 00's raw_item_00.json (kinjobales_wholesale) — real
# field names, real shapes, shortened values.
REAL_ITEM = {
    "id": "7665294006422654226",
    "text": "#kenyantiktok #finegirl #nairobitiktokers #fypp #goviral ",
    "webVideoUrl": "https://www.tiktok.com/@kinjobales_wholesale/video/7665294006422654226",
    "authorMeta": {
        "name": "kinjobales_wholesale",
        "nickName": "KINJO BALES",
        "signature": "NAIROBI: kampala center 4th floor 0727910437",
        "fans": 1400000,
        "avatar": "https://p16.tiktokcdn-us.com/some-avatar.jpg",
    },
    "videoMeta": {"coverUrl": "https://p16.tiktokcdn-us.com/some-cover.jpg", "duration": 37},
    "hashtags": [{"name": "kenyantiktok"}, {"name": "duvets"}, {"id": "x"}],  # one entry lacks name
    "playCount": 1718,          # extra fields must be tolerated, not fatal
    "isSlideshow": False,
}


def test_real_shaped_item_parses():
    v = TikTokVideo.model_validate(REAL_ITEM)
    assert v.id == "7665294006422654226"
    assert v.authorMeta.fans == 1_400_000
    assert "0727910437" in v.authorMeta.signature   # bio survives verbatim
    assert v.videoMeta.duration == 37


def test_hashtag_names_flattens_and_skips_nameless():
    v = TikTokVideo.model_validate(REAL_ITEM)
    assert v.hashtag_names == ["kenyantiktok", "duvets"]  # nameless entry skipped


def test_missing_cover_is_tolerated():
    """Some videos have no cover — that's data, not an error. The draft
    agent copes; validation must not reject the whole video."""
    item = {**REAL_ITEM, "videoMeta": {"duration": 12}}
    v = TikTokVideo.model_validate(item)
    assert v.videoMeta.coverUrl is None


def test_garbage_is_rejected_at_the_border():
    """An item without the fields BOB depends on must fail HERE — loudly —
    not three layers deeper as a mystery AttributeError."""
    with pytest.raises(ValidationError):
        TikTokVideo.model_validate({"something": "else entirely"})


@pytest.mark.parametrize(
    ("pasted", "expected"),
    [
        ("kinjobales_wholesale", "kinjobales_wholesale"),
        ("@kinjobales_wholesale", "kinjobales_wholesale"),
        ("  @kinjobales_wholesale  ", "kinjobales_wholesale"),
        ("https://www.tiktok.com/@kinjobales_wholesale", "kinjobales_wholesale"),
        ("https://www.tiktok.com/@mama.wanjiku?lang=en", "mama.wanjiku"),
    ],
)
def test_seller_input_normalizes(pasted, expected):
    """Sellers paste handles every which way; all of them must work."""
    assert normalize_username(pasted) == expected
