"""
Scraper service — TikTok data in, validated objects out. (Session 1.2)

    seller's handle ──> Apify actor run ──> raw JSON ──> pydantic validation ──> TikTokVideo objects
                        (clockworks/                     (reject garbage          + covers stored
                         tiktok-scraper)                  at the border)            by US

This is the ADAPTER for our scrape engine (workplan: data source strategy).
Callers see `fetch_profile()` and `TikTokVideo` — they never see Apify.
Swapping to TikTok's Display API later means rewriting THIS file only.

Design rules (the production-grade POC bar):
    1. Every external response is schema-validated before anyone touches it.
       Third-party JSON is guilty until proven parseable (pydantic is judge).
    2. Timeouts on everything; failures raise ScraperError with a human message.
    3. Cover images are downloaded and stored by us — TikTok CDN URLs expire
       (spike 00's #1 gotcha).
"""

import re

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import PROJECT_ROOT, settings

# ── CONFIG ────────────────────────────────────────────────────────────────────
APIFY_BASE = "https://api.apify.com/v2"

# Resolved from our real console run (run Z7EY84Fcl1wMg3SL6 → actId), not
# guessed. If we ever switch actors, the INPUT SHAPE below must be re-derived
# the same way: run once in the console, then GET the run's INPUT record.
ACTOR_ID = "GdWCkxBtKWOsKjdch"  # clockworks/tiktok-scraper

# Actor runs scrape a live site — they take tens of seconds. run-sync holds
# the HTTP connection open until the run finishes (Apify caps this at 300s);
# we allow 120s before declaring failure. Cover downloads are plain CDN GETs.
RUN_TIMEOUT_S = 120
DOWNLOAD_TIMEOUT_S = 30

# Where OUR copies of cover images live. Local disk for the POC (served as
# static files); the swap to object storage (S3/R2) later touches only
# save_cover(). Gitignored — scraped media never enters git.
MEDIA_DIR = PROJECT_ROOT / "backend" / "media" / "covers"


class ScraperError(Exception):
    """Any scrape failure, with a message fit for a log AND a human."""


# ── SCHEMAS (the validation border) ───────────────────────────────────────────
# These mirror ONLY the fields we proved exist in spike 00's raw payload.
# Unknown fields are ignored; missing REQUIRED fields fail loudly here —
# never deeper in the app where the error would make no sense.
class TikTokAuthor(BaseModel):
    name: str                              # handle, e.g. "kinjobales_wholesale"
    nickName: str = ""
    signature: str = ""                    # the bio — holds addresses/phones (spike 00)
    fans: int = 0
    avatar: str | None = None


class _VideoMeta(BaseModel):
    coverUrl: str | None = None            # EXPIRING CDN link — download, never store
    duration: int = 0


class TikTokVideo(BaseModel):
    """One scraped video, validated. This is what the rest of BOB consumes."""

    id: str                                # TikTok's video id → products.tiktok_video_id
    text: str = ""                         # caption (hashtag soup, per spike 00)
    webVideoUrl: str
    authorMeta: TikTokAuthor
    videoMeta: _VideoMeta
    hashtags: list[dict] = Field(default_factory=list)

    @property
    def hashtag_names(self) -> list[str]:
        """Flatten Apify's [{'name': 'duvets'}, ...] to ['duvets', ...] —
        the weak category hints the draft agent uses."""
        return [h["name"] for h in self.hashtags if h.get("name")]


# ── HELPERS ───────────────────────────────────────────────────────────────────
def normalize_username(raw: str) -> str:
    """Sellers will paste '@handle', a profile URL, or a bare handle —
    accept all three. A pure function so tests can hammer it without
    touching the network."""
    raw = raw.strip().lstrip("@")
    if m := re.search(r"tiktok\.com/@([\w.]+)", raw):
        return m.group(1)
    return raw


# ── ENGINE: Apify ─────────────────────────────────────────────────────────────
def fetch_profile(username: str, limit: int = 10) -> list[TikTokVideo]:
    """Scrape a seller's latest videos. Returns validated TikTokVideo objects.

    Uses Apify's run-sync-get-dataset-items: trigger the actor AND get its
    dataset back in one call — no run-polling loop needed at our scale.
    Input shape copied verbatim from our proven console run.
    """
    if not settings.apify_api_token:
        raise ScraperError(
            "APIFY_API_TOKEN is not set — add it to .env (see .env.example)."
        )

    username = normalize_username(username)

    try:
        resp = httpx.post(
            f"{APIFY_BASE}/acts/{ACTOR_ID}/run-sync-get-dataset-items",
            headers={"Authorization": f"Bearer {settings.apify_api_token}"},
            json={
                # The proven input shape (console run, 2026-07-22):
                "profiles": [username],
                "resultsPerPage": limit,
                "profileScrapeSections": ["videos"],
                "commentsPerPost": 0,          # we don't need comments — don't pay for them
            },
            timeout=RUN_TIMEOUT_S,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise ScraperError(
            f"Apify run failed for @{username}: HTTP {e.response.status_code}"
        ) from e
    except httpx.RequestError as e:
        raise ScraperError(f"Could not reach Apify for @{username}: {e}") from e

    items = resp.json()
    videos: list[TikTokVideo] = []
    for raw in items:
        try:
            videos.append(TikTokVideo.model_validate(raw))
        except ValidationError:
            # One malformed item must not sink the whole scrape — skip it.
            # (If Apify changes its schema wholesale, EVERY item fails and
            # the empty-result error below fires — which is what we'd want.)
            continue

    if not videos:
        raise ScraperError(
            f"No usable videos for @{username} — wrong handle, private account, "
            "or the actor's output schema changed."
        )
    return videos


def save_cover(video: TikTokVideo) -> str | None:
    """Download OUR copy of the cover image; return its relative path.

    Spike 00's #1 gotcha made policy: TikTok cover URLs are signed and expire
    in hours. We store the bytes under our media dir, named by video id
    (idempotent — re-scraping overwrites the same file, no duplicates).
    Returns None when the video has no cover; callers decide how to cope.
    """
    if not video.videoMeta.coverUrl:
        return None

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    dest = MEDIA_DIR / f"{video.id}.jpg"
    try:
        resp = httpx.get(video.videoMeta.coverUrl, timeout=DOWNLOAD_TIMEOUT_S)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    except httpx.HTTPError as e:
        raise ScraperError(f"Cover download failed for video {video.id}: {e}") from e

    # Stored as a path relative to media root — what the DB will hold. The
    # public URL prefix gets attached at serve time, so moving to S3 later
    # doesn't invalidate every DB row.
    return f"covers/{video.id}.jpg"
