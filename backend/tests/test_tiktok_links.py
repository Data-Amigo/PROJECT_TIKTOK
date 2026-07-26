"""TikTok link → video id. Pure/deterministic — no network (the short-link path
is exercised with an injected fake resolver)."""

import pytest

from app.services import tiktok_links

VID = "7662081322675932424"


@pytest.mark.parametrize(
    "text",
    [
        f"https://www.tiktok.com/@classycloset/video/{VID}",
        f"https://www.tiktok.com/@classycloset/video/{VID}?is_from_webapp=1&sender_device=pc",
        f"https://m.tiktok.com/v/{VID}.html",
        f"https://www.tiktok.com/@shop/photo/{VID}",  # TikTok photo mode
        f"check this out 👉 https://www.tiktok.com/@shop/video/{VID} 🔥",  # link in a blob
    ],
)
def test_extract_pulls_id_from_full_links(text):
    assert tiktok_links.extract_video_id(text) == VID


def test_extract_returns_none_for_a_short_link():
    # A short link has no id in it yet — resolve_video_id follows it instead.
    assert tiktok_links.extract_video_id("https://vm.tiktok.com/ZMabcдef/") is None


def test_extract_ignores_stray_numbers_that_are_not_tiktok():
    # A bare number with no TikTok context must NOT be mistaken for a video id.
    assert tiktok_links.extract_video_id("bei ni 600, size 32") is None


def test_resolve_follows_a_short_link_via_injected_resolver():
    def fake_resolver(url):
        assert url == "https://vm.tiktok.com/ZMabc123/"
        return f"https://www.tiktok.com/@classycloset/video/{VID}"

    got = tiktok_links.resolve_video_id("https://vm.tiktok.com/ZMabc123/", _resolver=fake_resolver)
    assert got == VID


def test_resolve_does_not_call_network_for_a_full_link():
    def boom(url):  # must never run — the id is already in the URL
        raise AssertionError("resolver should not be called for a full link")

    got = tiktok_links.resolve_video_id(f"https://www.tiktok.com/@x/video/{VID}", _resolver=boom)
    assert got == VID


def test_resolve_returns_none_for_a_non_tiktok_url():
    assert tiktok_links.resolve_video_id("https://example.com/whatever") is None
