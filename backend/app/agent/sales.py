"""
Sales agent 🤖 — the customer-facing chat on the public shop page. (M5.1)

    buyer's question + the shop's catalogue ──> Claude ──> a helpful reply
                                                (context injection, NOT RAG)

This is the "SokoLink Agent" from the vision — the WhatsApp close, on the web.
For now it ANSWERS (product Q&A, find-me-something); the actual "Buy Now"
(M-Pesa STK) is M4, wired in later. Per rails-before-agent, the agent can talk
about money but cannot move it until the payment rails exist.

WHY Anthropic here (and OpenAI for vision): Fredrick's split — Claude runs the
conversation, GPT reads the product images. This file is the only place that
knows we use Claude for chat.

Grounding: the shop's whole (small) catalogue is injected into the system
prompt — DIRECT context injection, not RAG. We always know exactly which shop's
products are relevant (there's no 10,000-doc search problem), so a plain lookup
beats a vector database. See CONCEPTS §2.
"""

from anthropic import Anthropic, RateLimitError
from pydantic import BaseModel

from app.config import settings

# claude-haiku-4-5: fast + cheap, right for a HIGH-VOLUME customer chat that
# answers product questions (incl. Swahili/Sheng). Bump to claude-sonnet-5 or
# claude-opus-4-8 here if answer quality needs it — one constant.
MODEL = "claude-haiku-4-5"
MAX_TOKENS = 500


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
        f"You are the friendly sales assistant for **{shop_name}**, a Kenyan shop on SokoLink.",
        "Help the customer find and decide on items from THIS shop only. Be warm, concise "
        "(1-3 short sentences), and reply in the customer's language — including Swahili and "
        "Sheng if they use it.",
        "",
        "Rules:",
        "- Only discuss products in the catalogue below. Never invent an item, price, colour, "
        "or size that isn't listed. If they ask for something not in stock, say so and suggest "
        "the closest thing that IS listed.",
        "- Prices are in Kenyan shillings (KES). If a price isn't set, say the seller will confirm it.",
        "- You cannot take payment yet: if the customer wants to buy, tell them checkout with "
        "M-Pesa is launching very soon, and suggest they note the item name. Do not ask for card "
        "or M-Pesa details.",
        "- Never ask for or reveal phone numbers.",
        "",
        "Catalogue:",
    ]
    for item in catalogue:
        price = f"KES {item.price_kes}" if item.price_kes is not None else "price on request"
        stock = "in stock" if item.available else "SOLD OUT"
        desc = f" — {item.description}" if item.description else ""
        lines.append(f"- {item.name} ({price}, {stock}){desc}")
    if not catalogue:
        lines.append("- (nothing published yet)")
    if featured is not None:
        lines += [
            "",
            f"The customer arrived from a video featuring: **{featured.name}**. Greet them with "
            "that item and offer to help, unless they ask about something else.",
        ]
    return "\n".join(lines)


def answer(
    shop_name: str,
    catalogue: list[CatalogueItem],
    history: list[dict],
    featured: CatalogueItem | None = None,
) -> str:
    """Produce the agent's next reply. `history` is the conversation so far as
    Anthropic messages ([{role, content}], starting with the buyer's 'user')."""
    if not settings.anthropic_api_key:
        raise SalesError("ANTHROPIC_API_KEY is not set — add it to .env.")

    client = Anthropic(api_key=settings.anthropic_api_key)
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_system_prompt(shop_name, catalogue, featured),
            messages=history,
        )
    except RateLimitError as e:
        raise SalesError("The assistant is busy right now — please try again in a moment.") from e
    except Exception as e:
        raise SalesError("The assistant had a hiccup — please try again.") from e

    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    return text or "Sorry, I didn't catch that — could you rephrase?"
