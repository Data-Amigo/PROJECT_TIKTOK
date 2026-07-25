"""
Draft agent 🤖 — a cover image becomes a product draft. (Session 1.2, part 2)

    cover image + caption + hashtags ──> Gemini (vision) ──> ProductDraft
                                          structured output   {name, description, tags}
                                                              seller CONFIRMS; never price/stock

WHY Gemini here (and Anthropic elsewhere): Fredrick tested both on real Kenyan
seller content and Gemini reads Sheng/Swahili in-video text noticeably better.
This file is the ONLY place that knows that — callers see draft_from_video().
Swap the model, or swap Gemini for another engine, and nothing upstream changes.

TWO lessons this file teaches — the heart of safe LLM integration:

  1. STRUCTURED OUTPUT. We don't ask the model for JSON and pray. We hand it a
     schema (ProductDraft) and the API is CONSTRAINED to return exactly that
     shape — no prose, no "```json" fences, no missing keys. Parsing hope is
     replaced by a guarantee.

  2. THE AGENT PROPOSES, CODE DISPOSES. ProductDraft has NO price and NO stock
     field — by construction the model cannot set them. It drafts words; the
     seller sets money with one tap; the DB constraint from 1.1 is the backstop.
     An LLM misreading "bei 800" must never be able to publish a price.
"""

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import settings

# ── CONFIG ────────────────────────────────────────────────────────────────────
# gemini-3.6-flash: current flash tier — cheap, fast, strong multilingual
# vision, supports the structured-output constraint below. (2.5-flash is now
# blocked for new API users, so we're on the current line — this is exactly
# the one-line swap this constant exists for.)
MODEL = "gemini-3.6-flash"

# Low temperature: this is extraction, not creative writing. We want the same
# image to yield the same draft, and we want it to describe what it SEES, not
# invent flattering copy.
TEMPERATURE = 0.2


class DraftError(Exception):
    """Any failure producing a draft, with a message fit for log and human."""


# ── OUTPUT SCHEMA (the guarantee + the guardrail) ─────────────────────────────
class ProductDraft(BaseModel):
    """What the agent is ALLOWED to produce. Notice what's absent: price, stock,
    seller contact. The schema itself is the guardrail — the model literally
    cannot return a price because there is nowhere to put one."""

    name: str = Field(description="Short product title a shopper would recognise, e.g. 'Fluffy Duvet Set'")
    description: str = Field(description="1-2 plain sentences describing the item, in English")
    tags: list[str] = Field(description="3-6 lowercase category keywords, e.g. ['duvet', 'bedding']")
    language_note: str = Field(
        default="",
        description="If the caption/image text was Swahili or Sheng, the key phrase you translated; else empty",
    )


# ── PROMPT ────────────────────────────────────────────────────────────────────
# Kept as a constant so it's reviewable and diffable — prompts are code.
# Note the explicit "do NOT guess price" line: defense in depth even though the
# schema already makes price impossible.
SYSTEM_INSTRUCTION = """You turn a Kenyan social-commerce seller's TikTok video \
cover image into a clean product draft.

The seller sells real physical goods (clothes, shoes, homeware, bags). Captions \
are mostly hashtags and are rarely useful. The COVER IMAGE is your main source — \
read any text printed on it, including Swahili and Sheng, and identify the product.

Rules:
- Describe only what you can actually see or read. Do not invent details.
- NEVER state or guess a price, phone number, or stock quantity. Those are the \
seller's to set, not yours.
- Keep the name short and the description to one or two plain English sentences.
- If you genuinely cannot tell what the product is, say so in the name \
("Unclear — needs seller review") rather than guessing."""


# ── AGENT ─────────────────────────────────────────────────────────────────────
def draft_from_video(
    cover_bytes: bytes | None,
    caption: str = "",
    hashtags: list[str] | None = None,
) -> ProductDraft:
    """Produce a product draft from a cover image (+ weak text hints).

    `cover_bytes` is OUR stored copy of the image (never a live TikTok URL —
    those expire; see scraper.save_cover). Returns a validated ProductDraft the
    seller will confirm and price. Raises DraftError on any failure — the UI
    shows the seller a "couldn't read that, try again", never a stack trace.
    """
    if not settings.gemini_api_key:
        raise DraftError("GEMINI_API_KEY is not set — add it to .env (see .env.example).")
    if cover_bytes is None:
        # No image = nothing to look at. The scraper returns None covers as
        # data, so this is an expected branch, not a crash.
        raise DraftError("No cover image to draft from.")

    hashtags = hashtags or []
    # The text hints go in the user turn; the image is the star. Hashtags are
    # labelled as weak on purpose so the model doesn't over-trust them.
    user_text = (
        f"Caption (mostly hashtags, low value): {caption!r}\n"
        f"Hashtags (weak category hints): {', '.join(hashtags) or 'none'}\n"
        "Draft the product from the cover image above."
    )

    client = genai.Client(api_key=settings.gemini_api_key)
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=cover_bytes, mime_type="image/jpeg"),
                user_text,
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=TEMPERATURE,
                # THIS pair is the structured-output guarantee: the response is
                # constrained to valid JSON matching ProductDraft. resp.parsed
                # then hands us a real ProductDraft, already validated.
                response_mime_type="application/json",
                response_schema=ProductDraft,
            ),
        )
    except Exception as e:  # google-genai raises various API errors; treat uniformly
        raise DraftError(f"Gemini draft call failed: {e}") from e

    draft = resp.parsed
    if not isinstance(draft, ProductDraft):
        # Extremely rare with structured output, but never trust — validate.
        raise DraftError("Gemini returned an unparseable draft.")
    return draft


# ── SMOKE TEST ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Live check against a real stored cover. Run AFTER the scraper has saved
    # one (or point at spike 00's cover). Costs a fraction of a shilling.
    #   backend/.venv/Scripts/python -m app.agent.draft
    import sys
    from pathlib import Path

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # emojis in captions

    # Reuse spike 00's downloaded cover if present.
    sample = Path(__file__).resolve().parents[2] / "spikes" / "out" / "cover_00.jpg"
    if not sample.exists():
        sys.exit(f"No sample cover at {sample} — run spike 00 first.")

    print(f"Drafting from {sample.name} ...")
    d = draft_from_video(
        cover_bytes=sample.read_bytes(),
        caption="#kenyantiktok #duvets #fypp",
        hashtags=["kenyantiktok", "duvets", "fypp"],
    )
    print(f"  name:        {d.name}")
    print(f"  description: {d.description}")
    print(f"  tags:        {d.tags}")
    print(f"  language:    {d.language_note or '(none)'}")
    print("\nNEXT STEP: the seller confirms this draft and adds price + stock (M1.3 API).")
