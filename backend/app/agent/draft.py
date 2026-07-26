"""
Draft agent 🤖 — a cover image becomes a product draft. (Session 1.2, part 2)

    cover image + caption + hashtags ──> OpenAI (vision) ──> ProductDraft
                                          structured output   {name, description, price?…}
                                                              seller CONFIRMS; publish = human gate

WHY OpenAI here: Fredrick has OpenAI billing, so we use GPT vision for extraction
instead of Gemini's capped free tier. (OpenAI now runs the customer sales chat
too — see agent/sales.py.) THIS FILE is the only place that knows which vision
provider we use — callers just see draft_from_video(). Swapping the model or the
whole provider is a change here and nowhere else (the adapter pattern).

TWO lessons this file teaches — the heart of safe LLM integration:

  1. STRUCTURED OUTPUT. We don't ask the model for JSON and pray. We hand it a
     schema (ProductDraft) and the API is CONSTRAINED to return exactly that
     shape — no prose, no "```json" fences, no missing keys. Parsing hope is
     replaced by a guarantee.

  2. THE AGENT PROPOSES, CODE DISPOSES. The AI drafts words and a price it can
     READ off the image — but a product is never LIVE until the seller hits
     Publish (which still requires a price). The AI removes typing; it can't
     sell anything at an unconfirmed price. See CONCEPTS §4.
"""

import base64

from openai import OpenAI, RateLimitError
from pydantic import BaseModel, Field

from app.config import settings

# ── CONFIG ────────────────────────────────────────────────────────────────────
# gpt-4o-mini: cheap, fast, vision-capable, supports the structured-output
# constraint below, and strong enough at OCR + multilingual (Sheng/Swahili) for
# reading a product + a printed price. Bump to gpt-4o (or a gpt-5 mini) here if
# quality needs it — this one constant is the whole model choice.
MODEL = "gpt-4o-mini"

# Low temperature: this is extraction, not creative writing. Same image →
# same draft; describe what's SEEN, don't invent flattering copy.
TEMPERATURE = 0


class DraftError(Exception):
    """Any failure producing a draft, with a message fit for log and human."""


class DraftQuotaError(DraftError):
    """The vision model hit its usage/billing cap (HTTP 429). Distinct so the
    API can return 429 and the UI can say 'try later', not 'broken'."""


# ── OUTPUT SCHEMA (the guarantee + the guardrail) ─────────────────────────────
class ProductDraft(BaseModel):
    """What the agent is ALLOWED to produce.

    The agent drafts name/description/tags and may fill `suggested_price_kes`
    ONLY from a price it can literally SEE ("600 ksh"). That becomes a DRAFT
    price; going live is always the seller's explicit Publish (CONCEPTS §4).
    There is deliberately NO `stock` field: stock is never something a picture
    can tell us.
    """

    is_product: bool = Field(
        description="True if the video shows a specific physical product a shopper could buy; "
        "false for replies, skits, announcements, or general hype with no clear item"
    )
    not_product_reason: str = Field(
        default="",
        description="If is_product is false, a short reason (e.g. 'reply video, no product shown'); else empty",
    )
    name: str = Field(description="Short product title a shopper would recognise, e.g. 'Fluffy Duvet Set'")
    description: str = Field(description="1-2 plain sentences describing the item, in English")
    tags: list[str] = Field(description="3-6 lowercase category keywords, e.g. ['duvet', 'bedding']")
    suggested_price_kes: int | None = Field(
        default=None,
        description="Whole Kenyan shillings, ONLY if a price is clearly printed on the image or "
        "stated in the caption (e.g. '600 ksh', 'KES 800', 'bei 500', '600/='). If no price is "
        "clearly shown, null. NEVER guess, estimate, or invent a price.",
    )
    language_note: str = Field(
        default="",
        description="If the caption/image text was Swahili or Sheng, the key phrase you translated; else empty",
    )


# ── PROMPT ────────────────────────────────────────────────────────────────────
# Kept as a constant so it's reviewable and diffable — prompts are code.
SYSTEM_INSTRUCTION = """You turn a Kenyan social-commerce seller's TikTok video \
cover image into a clean product draft.

The seller sells real physical goods (clothes, shoes, homeware, bags). Captions \
are mostly hashtags and are rarely useful. The COVER IMAGE is your main source — \
read any text printed on it, including Swahili and Sheng, and identify the product.

Rules:
- First decide is_product: does this video show a specific physical item a shopper \
could buy? Reply/duet/skit/announcement videos, or general hype with no clear \
product, are is_product=false with a short not_product_reason. When false, still \
fill your best-guess name/description from whatever is visible.
- Describe only what you can actually see or read. Do not invent details.
- PRICE: sellers often print the price right on the cover ("clogs 600 ksh", \
"650 ksh", "KES 800", "bei 500", "600/="). If you can clearly READ a price for \
this product, put the whole-shilling number in suggested_price_kes. If no price \
is clearly shown, leave it null. NEVER guess or estimate a price — a wrong \
suggested price is worse than none.
- NEVER output a phone number or a stock quantity. Those are the seller's alone.
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
    seller will confirm. Raises DraftError on any failure — the UI shows the
    seller a plain message, never a stack trace.
    """
    if not settings.openai_api_key:
        raise DraftError("OPENAI_API_KEY is not set — add it to .env (see .env.example).")
    if cover_bytes is None:
        raise DraftError("No cover image to draft from.")

    hashtags = hashtags or []
    # The text hints go in the user turn; the image is the star. Hashtags are
    # labelled weak on purpose so the model doesn't over-trust them.
    user_text = (
        f"Caption (mostly hashtags, low value): {caption!r}\n"
        f"Hashtags (weak category hints): {', '.join(hashtags) or 'none'}\n"
        "Draft the product from the cover image."
    )
    b64 = base64.b64encode(cover_bytes).decode("ascii")

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        completion = _parse(
            client,
            model=MODEL,
            temperature=TEMPERATURE,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                },
            ],
            # Structured output: the response is CONSTRAINED to ProductDraft's
            # schema; `.parsed` hands back a validated ProductDraft.
            response_format=ProductDraft,
        )
    except RateLimitError as e:
        # 429 — rate limit or exhausted billing. One friendly message for both.
        raise DraftQuotaError(
            "The image reader has reached its usage limit. Try again shortly, or "
            "check the OpenAI billing. You can still fill in the details by hand."
        ) from e
    except Exception as e:
        raise DraftError(
            "Couldn't read this image automatically — please fill in the details manually."
        ) from e

    message = completion.choices[0].message
    if getattr(message, "refusal", None):
        raise DraftError("The image reader declined to read this image.")
    draft = message.parsed
    if not isinstance(draft, ProductDraft):
        raise DraftError("The image reader returned an unparseable draft.")
    return draft


def _parse(client: OpenAI, **kwargs):
    """Call the structured-output parse helper, whichever path this SDK exposes
    (it moved out of the `beta` namespace across versions — support both)."""
    parse = getattr(client.chat.completions, "parse", None)
    if parse is not None:
        return parse(**kwargs)
    return client.beta.chat.completions.parse(**kwargs)


# ── SMOKE TEST ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    #   backend/.venv/Scripts/python -m app.agent.draft
    import sys
    from pathlib import Path

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # emojis in captions

    sample = Path(__file__).resolve().parents[2] / "spikes" / "out" / "cover_00.jpg"
    if not sample.exists():
        sys.exit(f"No sample cover at {sample} — run spike 00 first.")

    print(f"Drafting from {sample.name} with {MODEL} ...")
    d = draft_from_video(
        cover_bytes=sample.read_bytes(),
        caption="#kenyantiktok #duvets #fypp",
        hashtags=["kenyantiktok", "duvets", "fypp"],
    )
    print(f"  is_product:  {d.is_product}" + (f" — {d.not_product_reason}" if not d.is_product else ""))
    print(f"  name:        {d.name}")
    print(f"  description: {d.description}")
    print(f"  tags:        {d.tags}")
    print(f"  price seen:  {('KES ' + str(d.suggested_price_kes)) if d.suggested_price_kes else '(none printed)'}")
    print(f"  language:    {d.language_note or '(none)'}")
    print("\nNEXT STEP: the seller confirms this draft (price pre-filled if seen) and publishes.")
