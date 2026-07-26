"""
Sales agent 💬 — the customer-facing chat on the public shop page. (M5.1)

    buyer's question + the shop's catalogue ──> OpenAI ──> a helpful reply
                                                (context injection, NOT RAG)

This is the "SokoLink Agent" from the vision — the WhatsApp close, on the web.
For now it ANSWERS (product Q&A, find-me-something); the actual "Buy Now"
(M-Pesa STK) is M4, wired in later. Per rails-before-agent, the agent can talk
about money but cannot move it until the payment rails exist.

WHY OpenAI here (BOTH chat and vision now): Fredrick tested the chat in Swahili
and Sheng — the way real Kenyan customers actually type (mixed English +
Swahili) — and found GPT the more natural. So this file uses OpenAI too; the
Anthropic split is retired. THIS FILE is the only place that knows which chat
provider we use — callers just see answer().

HUMAN, not "assistant": the shopper should feel like they're chatting with the
real shop, not a bot. The persona speaks in the first person AS the shop, never
announces it's an AI, and the frontend labels the chat with the shop's own
name + avatar (see ShopExperience.tsx) — no robot badge.

Grounding: the shop's whole (small) catalogue is injected into the system
prompt — DIRECT context injection, not RAG. We always know exactly which shop's
products are relevant (there's no 10,000-doc search problem), so a plain lookup
beats a vector database. See CONCEPTS §2.
"""

from openai import OpenAI, RateLimitError
from pydantic import BaseModel

from app.config import settings

# gpt-4o (full, not -mini): this is the customer's first impression, and it must
# handle mixed English + Swahili + Sheng naturally — the full model is markedly
# better at that than -mini. Bump/swap here if cost or quality dictates — one
# constant is the whole model choice.
MODEL = "gpt-4o"
MAX_TOKENS = 500
# A little warmth (vs 0 for extraction): this is conversation, not OCR. Still
# low enough that the grounding rules below hold — it won't invent products.
TEMPERATURE = 0.4


class SalesError(Exception):
    """A chat failure with a message safe to show a buyer."""


class CatalogueItem(BaseModel):
    """One product as the agent sees it (already public/published)."""

    name: str
    price_kes: int | None
    available: bool
    description: str


def _system_prompt(shop_name: str, catalogue: list[CatalogueItem], featured: CatalogueItem | None) -> str:
    lines = [
        f"You ARE {shop_name}, a Kenyan seller chatting with a customer on your own online shop.",
        "Talk like a warm, real shopkeeper — first person ('tuko na…', 'we have…'), never in the "
        "third person about the shop. You are a person, not a bot: NEVER say you are an AI, an "
        "assistant, a language model, or 'here to help you shop'. Just chat naturally, like on WhatsApp.",
        "Keep replies short (1-3 sentences). Match the customer's language and mix exactly — if "
        "they write English, Swahili, or Sheng (or a mix), reply the same way. Warm, a little emoji.",
        "",
        "Rules (these are firm):",
        "- Only talk about products in the catalogue below. NEVER invent an item, price, colour, "
        "or size that isn't listed. If they want something you don't have, say so honestly and "
        "point them to the closest thing you DO have.",
        "- Prices are in Kenyan shillings (KES). If a price isn't set, say you'll confirm it.",
        "- You can't take payment on the chat yet: if they want to buy, tell them M-Pesa checkout "
        "is coming very soon and to note the item name. Never ask for card or M-Pesa PIN details.",
        "- Never ask for or give out phone numbers.",
        "",
        "Your stock right now:",
    ]
    for item in catalogue:
        price = f"KES {item.price_kes}" if item.price_kes is not None else "price on request"
        stock = "in stock" if item.available else "SOLD OUT"
        desc = f" — {item.description}" if item.description else ""
        lines.append(f"- {item.name} ({price}, {stock}){desc}")
    if not catalogue:
        lines.append("- (nothing listed yet)")
    if featured is not None:
        lines += [
            "",
            f"The customer just tapped a video showing your **{featured.name}**. Open with that "
            "item and offer to help, unless they ask about something else.",
        ]
    return "\n".join(lines)


def answer(
    shop_name: str,
    catalogue: list[CatalogueItem],
    history: list[dict],
    featured: CatalogueItem | None = None,
) -> str:
    """Produce the agent's next reply. `history` is the conversation so far as
    chat messages ([{role, content}], starting with the buyer's 'user')."""
    if not settings.openai_api_key:
        raise SalesError("OPENAI_API_KEY is not set — add it to .env.")

    client = OpenAI(api_key=settings.openai_api_key)
    messages = [{"role": "system", "content": _system_prompt(shop_name, catalogue, featured)}, *history]
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            messages=messages,
        )
    except RateLimitError as e:
        raise SalesError("The shop is busy right now — please try again in a moment.") from e
    except Exception as e:
        raise SalesError("Had a hiccup — please try again.") from e

    text = (resp.choices[0].message.content or "").strip()
    return text or "Pole, sijaelewa vizuri — unaweza rudia?"
