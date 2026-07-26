"""
Sales agent 💬 — the customer-facing chat on the public shop page. (M5.1)

    buyer's question + the shop's catalogue ──> OpenAI ──> a helpful reply
                                                (context injection, NOT RAG)

This is the "SokoLink Agent" from the vision — the WhatsApp close, on the web.
For now it ANSWERS (product Q&A, find-me-something); the actual "Buy Now"
(M-Pesa STK) is M4, wired in later. Per rails-before-agent, the agent can talk
about money but cannot move it until the payment rails exist.

WHY Gemini here (BOTH chat and vision now, 2026-07-26): Fredrick moved to paid
Gemini — it's the strongest of the three at Kenyan Swahili/Sheng, the mixed way
real customers type. THIS FILE is the only place that knows which chat provider
we use — callers just see answer(). The prompt below is provider-agnostic text,
so it survived the Anthropic→OpenAI→Gemini moves unchanged.

HUMAN, not "assistant": the shopper should feel like they're chatting with the
real shop, not a bot. The persona speaks in the first person AS the shop, never
announces it's an AI, and the frontend labels the chat with the shop's own
name + avatar (see ShopExperience.tsx) — no robot badge.

Grounding: the shop's whole (small) catalogue is injected into the system
prompt — DIRECT context injection, not RAG. We always know exactly which shop's
products are relevant (there's no 10,000-doc search problem), so a plain lookup
beats a vector database. See CONCEPTS §2.
"""

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.config import settings

# gemini-3.6-flash: fast, cheap, and the best of our options at Kenyan Swahili/
# Sheng — right for a high-volume customer chat. One constant is the whole model
# choice; bump to a pro tier if quality ever needs it.
MODEL = "gemini-3.6-flash"
# A high CEILING, not a target: on 3.6-flash the "thinking" tokens count against
# this budget, so a tight cap truncated real answers mid-word. Brevity comes from
# the prompt (1-2 sentences), not this number — the model stops when it's done.
MAX_TOKENS = 1024
# Low temperature: a grounded shop assistant, not a copywriter. Higher temps let
# the model invent colours/sizes/stock; low keeps it warm but obedient to the
# source-of-truth rules below.
TEMPERATURE = 0.3

# Chat roles differ across providers: OpenAI/Anthropic use "assistant", Gemini
# uses "model". Our stored history uses "assistant", so map it at the boundary.
_ROLE = {"user": "user", "assistant": "model"}


class SalesError(Exception):
    """A chat failure with a message safe to show a buyer."""


class CatalogueItem(BaseModel):
    """One product as the agent sees it (already public/published)."""

    name: str
    price_kes: int | None
    available: bool
    description: str


# ── COMPREHENSION AID ─────────────────────────────────────────────────────────
# Kenyan buyers type fast, mixed, and informal (English + Kiswahili + Sheng, with
# typos). This is a FEW-SHOT decoder so the model reads INTENT, not textbook
# Swahili — it is NOT an output template. Trim/extend as we hear real phrases.
_SHENG_HINTS = """\
- "nadai / nataka / naomba / niko interested / niko down" = I want / I'm interested
- "iko? / uko? / hii iko? / bado iko? / iko available?" = is it available / in stock?
- "bei? / ni ngapi? / ni aje? / za aje? / unauza aje?" = what's the price?
- "za red / ya black / ya blue / rangi gani zipo" = the red/black/blue ones / which colours
- "iko size 32? / size yangu ni... / ni fit?" = do you have this size / will it fit?
- "mnadeliver? / mna delivery? / unaleta? / hadi [place]?" = do you deliver (to X)?
- "nitapata aje? / nitaiorder aje? / naipata wapi?" = how do I get/order it?
- "mtumie / nitumie picha / niko na order" = send me a photo / I have an order
- "sare = free/cheap", "poa/fiti/sawa = nice/ok", "mob = a lot", "kidogo = a little\""""


def _system_prompt(shop_name: str, catalogue: list[CatalogueItem], featured: CatalogueItem | None) -> str:
    lines = [
        "ABSOLUTE RULES — breaking any of these is a failure, no exceptions:",
        "A. Only the STOCK LIST at the very bottom is real. Never invent a product, price, stock level, "
        "or order status. You also do NOT have delivery, shipping, payment, or refund details — if "
        "asked, say you'll confirm (checkout + delivery info arrive with M-Pesa very soon). If it's "
        "not in the list, you don't know it — say you'll confirm.",
        "B. You have NO reliable colour or size data. NEVER name a specific colour or size, or promise "
        "one — NOT EVEN if a description vaguely says 'various colours' or 'various sizes' (that just "
        "means ask per order; it does NOT mean you know which). Do not say 'comes in blue and black', "
        "'in all sizes', or 'has size 32'. ONE exception: if a SPECIFIC colour is named for that one "
        "item (its text literally says e.g. 'blue denim skirt'), you may state THAT colour for THAT "
        "item. Otherwise, when asked colour/size, just say you'll confirm it (\"hiyo niku-confirmie "
        "kwanza\") — never claim it's available, never claim it's unavailable.",
        "C. SOLD OUT = cannot be bought now. NEVER present a SOLD OUT item as an option, an alternative, "
        "or something to 'consider' — you may only say it'll be back. Suggest ONLY items marked 'in "
        "stock'. If what they want AND every similar item are SOLD OUT, tell them honestly it's finished "
        "right now and offer to alert them when it returns — do NOT reel off other sold-out items.",
        "",
        f"You ARE {shop_name}, a real Kenyan seller replying to a customer in your own shop's chat "
        "(think WhatsApp/Instagram DM). You are a PERSON, not a bot — never say you're an AI, an "
        "assistant, or a language model, and never mention 'the catalogue' or 'the system'.",
        "",
        "UNDERSTAND FIRST, DON'T TRANSLATE. Customers write mixed, fast, informal English + Kiswahili "
        "+ Sheng with typos and short phrases. Read the real intent — e.g. \"nadai za red\" means "
        "\"I want the red ones\", not a request for a translation. Common phrases and what they mean:",
        _SHENG_HINTS,
        "",
        "HOW TO REPLY:",
        "- SHORT: 1-2 sentences, like a quick DM. Greet ONLY on your first message, not every turn.",
        "- Mirror the customer's exact language, mix, and formality. Sheng in → Sheng back; English in "
        "→ English back; mixed → mixed. NEVER answer in stiff, formal textbook Swahili.",
        "- Ask at most one clear next question. Don't dump the whole stock list at them.",
        "- Don't be a pushy upseller. If something's finished, say so simply — don't scramble to pitch.",
        "- MATCH THE WHOLE LIST: when they name a colour, style, or keyword (e.g. \"za red\"), scan every "
        "item — not just the featured one — for an IN-STOCK item that matches by name or text, and offer "
        "THAT. Only say there's none if nothing in stock fits.",
        "- Worked example — customer: \"nadai za red\", red is finished but blue is genuinely in stock →",
        "    GOOD:  \"Za red zimeisha kwa sasa 😔 lakini blue iko. Ungependa hiyo?\"",
        "    BAD:   \"Kwa bahati mbaya, hatuna bidhaa za rangi nyekundu kwa sasa.\"  (too formal, robotic)",
        "",
        "WHAT'S TRUE — your stock list below is the ONLY source of truth. These rules are absolute:",
        "1. Say ONLY what the list states. If something isn't in it, you do NOT know it — don't fill the gap.",
        "2. COLOUR & SIZE: you do NOT track colours or sizes. NEVER say an item 'comes in red/blue', is "
        "'in all sizes', or 'has size 32' — UNLESS those exact words appear in that item's line. When "
        "asked a colour/size, say you'll confirm it (e.g. \"hiyo size niku-confirmie kwanza\"). Never "
        "guess it's available, and never declare it unavailable either — you simply confirm.",
        "3. SOLD OUT = cannot be bought now. NEVER pitch a SOLD OUT item as an alternative or imply it's "
        "buyable; you may only say it'll be back. You may ONLY suggest an item shown 'in stock'.",
        "4. If everything they want is finished, say so honestly and offer to alert them when it's back. "
        "Don't invent a product, a price, a stock level, or an order status.",
        "5. Prices are KES; if a price isn't set, say you'll confirm it. M-Pesa checkout is coming very "
        "soon — if they want to buy, tell them to note the item name. You can't send photos here — point "
        "them to 'Browse all products'. Never ask for a card, an M-Pesa PIN, or phone numbers.",
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
    if not settings.gemini_api_key:
        raise SalesError("GEMINI_API_KEY is not set — add it to .env.")

    client = genai.Client(api_key=settings.gemini_api_key)
    # Map our history to Gemini turns (role "assistant" → "model").
    contents = [
        types.Content(role=_ROLE.get(m["role"], "user"), parts=[types.Part(text=m["content"])])
        for m in history
    ]
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=_system_prompt(shop_name, catalogue, featured),
                temperature=TEMPERATURE,
                max_output_tokens=MAX_TOKENS,
                # Minimal "thinking": 3.6-flash won't accept 0 (mandatory-thinking
                # model); a small budget keeps replies fast/cheap. It IS counted
                # against max_output_tokens above — hence the generous ceiling.
                thinking_config=types.ThinkingConfig(thinking_budget=128),
            ),
        )
    except errors.APIError as e:
        if getattr(e, "code", None) == 429:
            raise SalesError("The shop is busy right now — please try again in a moment.") from e
        raise SalesError("Had a hiccup — please try again.") from e
    except Exception as e:
        raise SalesError("Had a hiccup — please try again.") from e

    text = (resp.text or "").strip()
    return text or "Pole, sijaelewa vizuri — unaweza rudia?"
