"""
Spike 00 — What does our Apify TikTok scraper actually give us?

    dataset id ──> Apify API ──> raw JSON items ──> field report ──> thumbnail
    (console run)   (GET)         (10 videos)        (printed)        (saved to disk)

Run it:
    backend/.venv/Scripts/python backend/spikes/spike_00_apify_tiktok.py

Pre-requisites:
    - .env at project root with APIFY_API_TOKEN=<token>   (never committed)
    - An Apify actor run that already succeeded (we did this in the console,
      2026-07-22: TikTok Scraper, 1 profile, 10 items).

Quick manual check: the script should print ~10 videos with author/caption/cover,
and one .jpg should appear in backend/spikes/out/.

Why this spike exists: the fields Apify returns will DIRECTLY shape our Product
model in M1. We look at real data before designing any schema — data first.
"""

import json
import sys
from pathlib import Path

# Windows terminals default to cp1252, which cannot print the emojis that are
# ALL OVER real TikTok captions (found out the hard way on first run). Force
# UTF-8 so print() never crashes on real-world text; errors="replace" means
# worst case we show ? instead of dying.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv
import os

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Project root = two levels up from this file (backend/spikes/ -> project root).
# We anchor paths here so the script works no matter where you run it from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The dataset produced by the console run on 2026-07-22 (run Z7EY84Fcl1wMg3SL6).
# NOTE: unnamed Apify datasets expire after a retention window (~7 days on the
# free plan) — fine for a spike, but the real service (M1) will trigger its own
# runs and read the dataset id from the run response, never hard-code it.
DATASET_ID = "oQKs7WdUeURgKRWzM"

APIFY_BASE = "https://api.apify.com/v2"

# Timeout on EVERY external call — a hung request should fail loudly, not hang
# the program. This habit carries into every service we build (POC quality bar).
TIMEOUT_S = 30

# Where downloaded thumbnails land. Gitignored — scraped media never goes in git.
OUT_DIR = Path(__file__).resolve().parent / "out"


# ── HELPERS ───────────────────────────────────────────────────────────────────
def load_token() -> str:
    """Read the Apify token from .env at project root.

    Fails fast with a human message if missing — a stranger running this
    should know exactly what to fix (that's the production-grade POC bar,
    applied even to a spike).
    """
    load_dotenv(PROJECT_ROOT / ".env")
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        sys.exit(
            "ERROR: APIFY_API_TOKEN not found.\n"
            f"Create {PROJECT_ROOT / '.env'} with a line:\n"
            "  APIFY_API_TOKEN=your_token_here"
        )
    return token


def fetch_items(token: str) -> list[dict]:
    """Pull all items from the run's dataset.

    Apify's model: an Actor RUN writes its results into a DATASET; the dataset
    is just a JSON array we can GET. The token goes in a header, not the URL —
    URLs end up in logs and shell history; headers don't. (Apify's console
    shows ?token=... URLs for convenience; we deliberately don't copy that.)
    """
    url = f"{APIFY_BASE}/datasets/{DATASET_ID}/items"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params={"format": "json"},
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()  # non-200 = crash with the real status, no guessing
    return resp.json()


def summarize_item(item: dict) -> dict:
    """Pluck the fields we THINK matter for a Product. Everything else is noise
    for now — but we print the full key list separately so nothing hides."""
    return {
        "author": item.get("authorMeta", {}).get("name"),
        "caption": (item.get("text") or "")[:120],  # first 120 chars is enough to judge
        "video_url": item.get("webVideoUrl"),
        "cover_url": item.get("videoMeta", {}).get("coverUrl"),
        "created": item.get("createTimeISO"),
        "views": item.get("playCount"),
    }


def download_thumbnail(url: str, dest: Path) -> None:
    """Download a cover image to disk.

    THE #1 GOTCHA of this whole data source: TikTok cover URLs are signed CDN
    links that EXPIRE (hours, not days). Hotlink them and every BOB Page goes
    blank by tomorrow. So the rule is: scrape -> download -> store OUR copy.
    This function is the proof that works.
    """
    resp = requests.get(url, timeout=TIMEOUT_S)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    token = load_token()

    print(f"Fetching dataset {DATASET_ID} ...")
    items = fetch_items(token)
    print(f"-> got {len(items)} items\n")

    if not items:
        sys.exit("Dataset is empty — check the run in the Apify console.")

    # 1) Full key inventory of the first item — so we see EVERYTHING the actor
    #    returns, not just what we guessed we'd want.
    print("=" * 70)
    print("ALL top-level keys on item[0]:")
    print(", ".join(sorted(items[0].keys())))
    print("=" * 70, "\n")

    # 2) The fields we believe matter, for every video — eyeball the captions:
    #    do sellers put prices in them? Sheng? phone numbers?
    for i, item in enumerate(items):
        s = summarize_item(item)
        print(f"[{i}] {s['author']}  ({s['created']}, {s['views']} views)")
        print(f"    caption: {s['caption']!r}")
        print(f"    video:   {s['video_url']}")
        print(f"    cover:   {(s['cover_url'] or 'MISSING')[:80]}...")
        print()

    # 3) Prove the download-and-store rule on the first cover image.
    first_cover = summarize_item(items[0])["cover_url"]
    if first_cover:
        OUT_DIR.mkdir(exist_ok=True)
        dest = OUT_DIR / "cover_00.jpg"
        download_thumbnail(first_cover, dest)
        print(f"Thumbnail saved -> {dest}  ({dest.stat().st_size / 1024:.0f} KB)")
    else:
        print("No cover URL on item[0] — note this for the Product model!")

    # 4) Keep one full raw item on disk for schema design reference in M1.
    OUT_DIR.mkdir(exist_ok=True)
    raw_path = OUT_DIR / "raw_item_00.json"
    raw_path.write_text(json.dumps(items[0], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Full raw item saved -> {raw_path}")

    print(
        "\nNEXT STEP: read the captions above with Fredrick — do sellers state "
        "prices? Then design the Product model (session 1.1) from what we saw."
    )
