# CONCEPTS — the "how it actually works" companion

> **Purpose.** The [WORKPLAN](WORKPLAN.md) says *what* we build and in what order.
> This file explains the *ideas* underneath — the agentic-system patterns, why we
> chose them, and (just as important) the popular ones we deliberately **don't**
> use. It grows as we add patterns. If you read one doc to understand the system,
> read this one.
>
> Written for someone learning to build end-to-end agentic systems, not just use them.

---

## 1. The one question that decides everything: where does the model get its context?

An LLM only knows two things: what it was trained on, and what you put in the
prompt. Every "AI architecture" is really just an answer to **"how do the right
facts get into the prompt at the right moment?"**

There are a few different answers, and picking the wrong one is the most common
beginner mistake:

| The facts live in… | You get them by… | The pattern is called… |
|---|---|---|
| A huge pile of documents, and you **don't know which** is relevant | Semantic search (embeddings + vector DB) | **RAG** |
| The **input itself** (an image, a pasted message) | Just… reading the input | **Extraction** |
| A database row you can fetch by a **known key** (this product, this seller) | A plain `SELECT` | **Direct context injection** |
| The result of an **action** (today's stock, a payment status) | Calling a function/tool | **Tool use** |

**Project TIKTOK uses the bottom three. It never uses RAG.** The next sections say
why, one at a time.

---

## 2. Why we are NOT using RAG (even though it's the famous one)

RAG — **R**etrieve, **A**ugment, **G**enerate — solves a specific problem:

> "I have 10,000 documents. A question comes in. I don't know *which* documents
> answer it, so I embed the question, find the most *semantically similar* chunks
> by vector distance, paste them into the prompt, and let the model answer."

The load-bearing word is **similar**. You use RAG when you must find relevant
information by *meaning*, because you don't have a key to look it up directly.

**BOB never has that problem.** Trace every place BOB needs information:

- *"What product is in this video?"* → the answer is **in the cover image** we're
  already holding. Nothing to search. → **extraction** (§3)
- *"Is this duvet cotton?"* (a future buyer question) → the answer is **one product
  row** we can fetch by ID. We already know the exact key. → **direct lookup** (§4)
- *"Is it still in stock?"* → the answer is a **live number in our DB**, changed by
  our payment callback. → **tool use / a query** (§5)

In each case we know *exactly* which fact we need. Retrieval-by-known-key is a
`SELECT`; retrieval-by-similarity is RAG. **Don't bring a vector database to a
`WHERE id = ?` problem.**

> **The contrast worth remembering.** The sibling project *Bonga na Mali*
> (insurance) **does** use RAG — "what does my policy cover?" means searching
> policy documents where you can't predict the relevant clause. Same brand (BOB),
> opposite information problem. Feeling *when* RAG fits is the lesson; the answer
> here is "it doesn't."

---

## 3. What the draft agent actually is: multimodal extraction + structured output

`backend/app/agent/draft.py` is our first 🤖 piece. Two patterns stack in it.

**Multimodal extraction.** We hand the model an image (+ weak text hints) and ask
it to pull out facts. The "context" is the pixels. There is no corpus, no search,
no embeddings — the source of truth arrived *in the request*. This is why a
hashtag-only caption like `#finegirl #kenyantiktok` is no obstacle: the model
reads the **image**, including Sheng/Swahili text printed on it.

**Structured output (constrained decoding).** The naive way to get JSON from an
LLM is to ask nicely and hope: `"reply with JSON"` → then pray it didn't wrap the
answer in ` ```json ` fences or add a chatty preamble. That breaks in production.

Instead we pass the model a **schema** (`ProductDraft`) and the API *constrains*
generation so the output can only be valid JSON matching that shape. We get back a
validated object, never a string to gamble on. Parsing-and-praying is replaced by
a guarantee.

```
cover image + hashtags ──▶ Gemini (schema = ProductDraft) ──▶ {name, description, tags}
                            constrained decoding              a real, validated object
```

---

## 4. The pattern that keeps money safe: "the agent proposes, code disposes"

This is the single most important design rule in the whole project, and it's what
separates a toy from something a stranger can trust with a payment.

**LLM output is always a *proposal*, never a *decision*, on anything that matters.**
Concretely, in `draft.py`:

- The `ProductDraft` schema has fields for `name`, `description`, `tags`.
- It has **no field for price and no field for stock.** By *construction* the model
  cannot set them — there's nowhere for a price to go.
- A test (`test_draft_schema_has_no_money_fields`) asserts this can never regress.

So even if the model misreads *"bei ni 800"* as *400*, it cannot publish a wrong
price — the number simply has no path into the system. The seller sets money with
one tap; deterministic Python and a database constraint own the truth.

Generalize it: **the LLM talks; code transacts.** The agent drafts words, suggests
timings, answers questions. Prices, stock decrements, payment status, consent — all
decided by plain code with hard rules. This is why an "agentic system" is ~20% LLM
calls and ~80% deterministic rails. We build the rails on purpose.

---

## 5. Patterns coming later (named now so you see them arrive)

- **Tool use / function calling** (M2–M3, the checkout/WhatsApp agent). The model
  is given a set of *typed functions* — `check_stock`, `create_order`,
  `send_stk_push` — and it chooses which to call. **The model decides *what* to do;
  our code decides *whether and how* it happens.** Every tool is a gate we control:
  validate inputs, require confirmation on anything irreversible, log everything.
- **Idempotency** (M3). Daraja can send the same payment callback twice. Code must
  make "process this payment" safe to run twice → the same order never fulfils
  twice. (This is a *rails* pattern, not an AI one — but it's why agents are safe.)
- **Human-in-the-loop approval** (M5, Reach). The LLM *drafts* a restock broadcast;
  the seller *approves* before it sends; code *enforces* the opt-in list, daily
  caps, and STOP. Proposes / disposes again, with a human in the middle.

- **Generative virtual try-on** (Phase 2, gated to specific businesses). The
  buyer uploads a photo of themselves; Gemini's *video generation* produces a clip
  of them wearing / using the product. This is a new pattern class for us —
  **generation**, not extraction: the model *creates* pixels rather than reading
  them. Its agentic shape is still proposes/disposes: it's a **tool** the buyer
  invokes and then previews-and-approves before it attaches to anything, and it
  sits behind hard rails because it's expensive and sensitive —
  a per-seller **feature flag / tier** (not every business gets it), **cost caps
  and rate limits** per buyer (video gen costs real money per clip), **content
  safety** on the uploaded photo, and **explicit consent** for using someone's
  likeness. Same principle as everywhere: the model proposes a clip; code decides
  whether it's allowed, how often, and for whom.

---

## 6. The frameworks & libraries — and why so few

A surprise for many: **we use no "AI framework."** No LangChain, no LlamaIndex, no
vector database, no orchestration library. The stack is deliberately plain:

| Layer | What we use | Why this and not a framework |
|---|---|---|
| Web API | **FastAPI** | Async, typed, tiny. You see every endpoint. |
| Data | **Postgres + SQLAlchemy + Alembic** | The DB is the source of truth; migrations version it. |
| Validation | **pydantic** | One tool for API schemas *and* LLM output schemas. |
| Vision LLM | **`google-genai` SDK, called directly** | Gemini reads Sheng/Swahili best (we tested). No wrapper. |
| Conversation LLM (later) | **`anthropic` SDK** | Reserved for the WhatsApp phase. |
| Scrape | **Apify**, behind our own `services/scraper.py` | An adapter we own, so the engine can be swapped. |

Why avoid the frameworks? They hide the mechanics you're here to learn — the loop,
the tool call, the schema, the retry. Calling the SDKs directly means **nothing is
magic**; when something breaks you can see exactly where. When the project is big
enough that a framework earns its complexity, we'll adopt it *knowing what it's
doing for us*. Not before.

---

## 7. One-paragraph summary to hold in your head

Project TIKTOK is an **agentic commerce system, not a RAG system.** The model's job
is to *look* (extract a product from an image) and later to *act* (drive a checkout
through typed tools) — never to *recall* facts from a document store, so there's no
retrieval-by-similarity anywhere. Everything the model produces is a **proposal**
that deterministic code validates before it touches money or stock. We use the
provider SDKs directly, with pydantic schemas as both the guardrail and the
guarantee, on a FastAPI + Postgres spine. RAG is a great tool — it's just the answer
to a question this project doesn't ask.
```

---

## Change log for this file

| Date | Added |
|------|-------|
| 2026-07-24 | Created after M1.2. Covers: context-source decision (§1), why-not-RAG (§2), extraction + structured output (§3), agent-proposes-code-disposes (§4), upcoming patterns (§5), the no-framework stack (§6). |
