"""
TikTok link → video id. (M5.2, part 1)

    a link the CUSTOMER pasted ──> the numeric video id ──> match a product

TikTok won't tell our page which video a shopper came from (no per-video link,
no referrer). So we flip it: the shopper taps "Copy link" on the video and
pastes it to us. This module turns whatever they paste into the video id we
store on each product (`Product.tiktok_video_id`).

Two shapes of pasted link:
  1. FULL   — https://www.tiktok.com/@shop/video/7662081322675932424?…
              The id is right there in the path — pure regex, no network.
  2. SHORT  — https://vm.tiktok.com/ZMabc…  (what the mobile app usually copies)
              The id is hidden behind a redirect, so we follow it ONCE to the
              real URL and read the id from there.

SSRF guard: we only ever make an outbound request to a known TikTok short-link
host, and we only read the resulting URL (never its body). A customer can't turn
this endpoint into a fetcher for arbitrary/internal addresses.
"""

import re
from urllib.parse import urlparse

import httpx

# Explicit id-bearing patterns, tried in order. Covers /video/<id>, TikTok photo
# mode /photo/<id>, the m.tiktok.com /v/<id>.html form, and an item_id= param.
_ID_PATTERNS = [
    re.compile(r"/(?:video|photo)/(\d{6,25})"),
    re.compile(r"/v/(\d{6,25})"),
    re.compile(r"[?&]item_id=(\d{6,25})"),
]
# Last resort: a long digit run, but ONLY when the text is clearly a TikTok link
# (guards against grabbing a price or phone number from stray pasted text).
_BARE_ID = re.compile(r"(\d{15,25})")

# Hosts whose links hide the id behind a redirect — the only hosts we'll call.
_SHORT_HOSTS = {"vm.tiktok.com", "vt.tiktok.com"}

# Any URL in a blob of pasted text (customers paste "check this https://… 🔥").
_URL_IN_TEXT = re.compile(r"https?://[^\s]+", re.IGNORECASE)

_RESOLVE_TIMEOUT_S = 5.0


def extract_video_id(text: str) -> str | None:
    """Pull the numeric video id straight out of pasted text — no network.

    Handles a full TikTok URL (with or without surrounding words/query params).
    Returns None for a short link (no id in it yet) — resolve_video_id follows
    those. Pure + deterministic, so it's the easy part to unit-test."""
    if not text:
        return None
    for pattern in _ID_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1)
    # Only fall back to a bare number if this really looks like a TikTok link.
    if "tiktok" in text.lower():
        m = _BARE_ID.search(text)
        if m:
            return m.group(1)
    return None


def _short_url(text: str) -> str | None:
    """The first URL in `text` whose host is a TikTok short-link host — the only
    kind we're willing to make a network request to."""
    for raw in _URL_IN_TEXT.findall(text):
        host = (urlparse(raw).hostname or "").lower()
        if host in _SHORT_HOSTS:
            return raw
    return None


def _follow_redirect(url: str) -> str | None:
    """Follow a TikTok short link to its real URL and return that URL (never its
    body). Host is re-checked here so this is safe to call in isolation."""
    host = (urlparse(url).hostname or "").lower()
    if host not in _SHORT_HOSTS:
        return None
    try:
        # follow_redirects lands us on the canonical /video/<id> URL; we only
        # read .url. A short timeout keeps a slow/hanging TikTok from stalling us.
        resp = httpx.get(url, follow_redirects=True, timeout=_RESOLVE_TIMEOUT_S)
        return str(resp.url)
    except httpx.HTTPError:
        return None


def resolve_video_id(text: str, *, _resolver=_follow_redirect) -> str | None:
    """Best-effort video id from whatever the customer pasted.

    Fast path: read the id directly (full URL). Slow path: if it's a short link,
    follow the redirect once and read the id from the real URL. Returns None if
    we genuinely can't tell — the caller then shows a friendly 'not found'.

    `_resolver` is injected so tests can exercise the short-link path without a
    real network call."""
    direct = extract_video_id(text)
    if direct:
        return direct
    short = _short_url(text)
    if not short:
        return None
    final = _resolver(short)
    return extract_video_id(final) if final else None
