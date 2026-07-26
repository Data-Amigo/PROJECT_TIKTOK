# WORKPLAN — Project TIKTOK (SokoLink)

> **How to read this file:** this is the living build plan. Each milestone (M0–M6)
> is broken into small **sessions** — one sitting each. A session ends with something
> that runs and a commit. We tick boxes as we go and never start a milestone until
> the previous one demos.
>
> **Learning goal:** by the end, Fredrick has built a complete end-to-end agentic
> system — not just used one. Every session says *what we build* and *what you learn*.
> Sessions marked 🤖 are the genuinely **agentic** parts; everything else is the
> plumbing an agent needs to stand on (and most of a real agent product IS plumbing —
> that's lesson #1).

---

## Ground rules (our working agreement)

0. **Document as we build.** Every session is documented in three places, no step
   skipped: the **status log** here (terse timeline), a **GitHub issue** (goal +
   done-when + what was learned), and — when a session introduces a new *idea* —
   [CONCEPTS.md](CONCEPTS.md), the evergreen learning companion. Code itself stays
   heavily commented (the *why*, not just the *what*).
1. **Explain → build → review → commit.** Before code is written we agree on what
   and why. After it works, we walk the code together before committing.
2. **Heavily commented code.** Comments explain *why*, not just what
   (house style: config banners, module docstrings with pipeline diagrams,
   "gotcha" notes, smoke-test blocks).
3. **Backend first, per feature:** `model → migration → service → API route → test`,
   then the UI that consumes it.
4. **One branch per milestone** (`m0-foundation`, `m1-bob-page`, …). Commit at each
   green test; merge to `main` when the milestone's "done when" is true.
5. **Deterministic money.** The LLM never decides prices, stock, or payment status.
   Daraja's callback is the only payment truth. The agent talks; code transacts.

---

## The architecture in one picture

```
TikTok/IG post                     seller pastes link
      │                                   │
      ▼                                   ▼
┌─────────────┐   scrape    ┌──────────────────────────┐
│  SokoLink Page   │ ◄────────── │  FastAPI backend          │
│ (Next.js)   │             │  api/ agent/ services/    │
│ sokolink/x  │             │  models/ ── Postgres      │
└─────┬───────┘             └────┬─────────────┬───────┘
      │ buyer fills order form   │             │
      ▼                          ▼             ▼
┌─────────────┐   STK push   ┌───────┐   ┌────────────┐
│ SokoLink Checkout│ ───────────► │Daraja │   │ Africa's   │
│ name·phone· │ ◄─────────── │M-Pesa │   │ Talking SMS│
│ consent     │   callback   └───────┘   └─────┬──────┘
└─────────────┘  = payment truth               │
                                               ▼
                                    SokoLink Reach: restock SMS
                                    (opt-in only, STOP honoured)
```

---

## Data source strategy (decided 2026-07-22)

**Apify is the scrape engine for now** (Fredrick has an actor picked + API key).
It pulls whole profiles without the seller logging in — closest to the
"she does almost nothing" goal, no approval wait, ~pennies at pilot scale.

```
now   Apify actor        →  profile/video data, no OAuth, no review wait
later TikTok Display API →  official "Connect TikTok" once app review passes
edge  oEmbed (free)      →  cheap fallback for a single pasted link
```

All engines hide behind the same `services/scraper.py` interface —
swapping engines is a one-file change, callers never know. (Adapter pattern.)

**Hard rules regardless of engine:** thumbnails are downloaded and stored by us
(TikTok CDN URLs expire); every external response is schema-validated before it
touches the DB; the Apify key lives in `.env` only.

---

## Quality bar: production-grade POC

Built so a stranger can test it without us in the room:
timeouts + retries + schema validation on every external call · designed error
states in the UI · secrets only in `.env` · tests on all money paths ·
logs that can reconstruct any incident.

---

## M0 — Foundation  `branch: m0-foundation`

*Goal: all services boot; `/health` returns 200.*

- [x] **0.0 Data spike** — `backend/spikes/spike_00_apify_tiktok.py` ran against
      a real seller (kinjobales_wholesale, 1.4M followers, 10 videos). Findings:
      **captions are hashtag soup — no prices, no product names** → the product
      draft must come from the COVER IMAGE (vision LLM) + hashtag category hints,
      seller confirms price. Bio carries shop addresses + phones → auto-fill
      onboarding. `commerceUserInfo` flags sellers. No transcriptions for
      Swahili content (own-ASR is a future project). Confirmed live: cover URLs
      expire (we store our own copy) and emojis are everywhere (UTF-8 or die).
      *You learned:* Apify's actor/run/dataset model; letting real data drive
      the schema instead of guessing.
- [x] **0.1 Backend skeleton** — venv, FastAPI app (`main.py`, `config.py`),
      liveness `/health`, pinned `requirements.txt`, first 2 tests green.
      Backend runs on **port 8100** (8000 belongs to mali-jubilee-poc on this
      machine). Design: /health = liveness only; readiness `checks` grow in 0.2.
      *You learned:* FastAPI anatomy, typed config via pydantic-settings,
      liveness vs readiness, in-process TestClient.
- [x] **0.2 Database layer** — Railway Postgres (SokoLink's OWN database — first
      URL was shared with 2 other projects incl. a `products` table collision;
      rule learned: one database per application). `db.py` with pool_pre_ping
      + pool_recycle (cloud DBs drop idle connections), Alembic wired to
      app config (single URL source), init migration applied, `/health` now
      reports db readiness. Redis + docker-compose deferred to M3 when
      idempotency actually needs them.
      *You learned:* engine-vs-session mental model, migrations as schema
      version control, blast radius, liveness-vs-readiness in practice.
- [x] **0.3 Frontend skeleton** — Next 16 + React 19 + Tailwind 4 via
      create-next-app; dev server on :3000. npm audit findings triaged (in
      Next's bundled deps; "fix" was a Next 9 downgrade — declined with eyes
      open). Placeholder .gitkeep dirs replaced by real scaffold; `[handle]`
      + `dashboard` routes return in M1 when they earn existence.
      *You learned:* App Router (folders = routes), server components (HTML
      to the phone, not JS bundles — the Kenyan-mobile reason), audit triage.
- [x] **0.4 Wire-up** — CORS middleware (origin-locked, wildcard forbidden,
      2 tests incl. evil-origin rejection); `lib/api.ts` as the frontend's only
      backend door; status page = server component rendering live /health with
      a designed backend-unreachable state. `NEXT_PUBLIC_` rule learned: values
      are INLINED into the browser bundle at build time — never secrets.
      *You learned:* CORS is a browser rule (server fetches skip it), Next 16
      fetch is uncached by default, the API-client-module pattern.

**Done when:** uvicorn + `npm run dev` boot and the frontend shows the backend
is healthy. ✅ MET 2026-07-23 — page renders api: ok · db: ok end to end.

---

## M1 — SokoLink Page  `branch: m1-bob-page`

*Goal: seller creates a page; public link shows item, price, Available/SOLD.*

- [x] **1.1 Models** — `Seller` + `Product` live on Railway (migration
      4c1e92d224d7, autogenerated AND reviewed line-by-line before applying).
      DB-level rails, each with a refusal test: stock ≥ 0 (overselling),
      unique tiktok_video_id (idempotent re-scrapes), published-needs-price
      (LLM can never push an unpriced draft live). Money = integer KES;
      availability derived, never stored. 10 tests green, rollback fixture
      keeps Railway at 0 rows.
      *You learned:* constraints as rails, money-as-integers, enum strategy,
      store-facts-compute-states, testing against a live DB without pollution.
- [x] **1.2 🤖 Scraper service** — `services/scraper.py`: Apify engine behind our
      own interface (`fetch_video`, `fetch_profile`) → caption, cover, metadata;
      thumbnails stored by us. First agentic piece: a VISION LLM reads the cover
      image (+ hashtag hints — spike 00 proved captions carry no product info)
      and drafts name/description/tags — the seller confirms; the LLM never
      sets price/stock.
      *You learn:* tool-building for agents, structured output, why we validate
      LLM output with schemas instead of trusting it.
- [x] **1.3 Products API** — `api/products.py` + `services/products.py` +
      `schemas/product.py`. Endpoints: `POST /api/products/ingest` (scrape→DRAFT,
      idempotent), `POST /api/products/{id}/autofill` (🤖 agent, words only —
      drafting split out as its own on-demand step so ingest stays cheap/fast),
      `PATCH /api/products/{id}` (seller sets price/stock, publish-needs-price),
      `GET /api/pages/{handle}` (buyer view, narrower shape). 9 tests (money
      path on real Postgres via rolled-back sessions; scraper+agent mocked);
      32 green. (#11)
      *You learned:* pydantic wire schemas vs DB models, service→route split,
      transactional test fixtures, error→HTTP-status mapping (502/400/404).
- [x] **1.4 Dashboard UI** — `app/dashboard/page.tsx` (paste handle → ingest →
      card grid) + `components/ProductCard.tsx` (auto-fill → edit → price/stock →
      publish; publish disabled without a price) + `lib/api.ts` typed client.
      Backend: `/media` static mount so covers display. Proven live end to end
      (ingest → cover serves → autofill named the product off the image →
      publish → public page). Typechecks + production-builds. (#12)
      *You learned:* client vs server components (this is a client component,
      talks to the backend from the browser → CORS), lifting state, the
      API-client-module pattern, designed loading/error/empty states.
- [x] **1.5 Public page** — `app/[handle]/page.tsx` (server component) +
      `PublicProductCard` + `OrderButton` + `not-found.tsx` + `error.tsx`.
      Production polish for real customer testing: rich OG/Twitter metadata
      (shared links preview on TikTok/WhatsApp), live stock (no-store fetch),
      real 404 vs error boundaries, mobile-first grid, honest "checkout coming
      soon" CTA. React `cache()` dedupes the metadata+page fetch. Verified live
      + screenshotted on a real published shop. (#13)
      *You learned:* server components + dynamic routes, generateMetadata/OG for
      social sharing, notFound() vs error boundaries, no-store for live data,
      why the public page reads stock from the DB not the scrape.

**Done when:** a seller pastes a real TikTok link and a public `sokolink/handle`
page shows the item with live availability. ✅ MET 2026-07-25 — proven live end
to end (kinjobales ingest → autofill → publish → public page renders the item,
price, Available badge).

---

> **⤳ Roadmap pivot (2026-07-25).** After M1, the model changed from
> "paste a handle each time" to an **account-first shop** ending in an
> **on-page agentic checkout**. Why: pasting a handle every time is too much
> seller work, and WhatsApp's agentic close is blocked by Meta — so we build
> the close *natively on the SokoLink page* (the original deck's "SokoLink Agent",
> relocated to the web where nobody can block it). The M-Pesa thesis is
> preserved: the agent collects the phone to send the STK, and that phone *is*
> the contact. Everything M1 built is reused — it just moves behind a login and
> a Content Inbox. Rails-before-agent still rules: the payment path is built
> and tested before the agent may call it.

## M1.6 — Smart drafting  `branch: smart-drafting`  *(done)*

*Interleaved before M2 to fix real-seller pain immediately.*

- [x] **1.6 Price-from-image + product detection** — the draft agent now reads a
      price printed on the cover (`suggested_price_kes`) and flags product vs
      non-product (`is_product`). Guardrail *refined not weakened*: the suggestion
      only PRE-FILLS the seller's price box ("read from image — confirm it"); the
      stored price is still written solely by the seller's PATCH (CONCEPTS §4).
      Proven live: real clog covers → KES 600/650/900 read correctly. 35 green.
      *You learned:* evolving a guardrail precisely, structured output with
      optional fields, human-confirms-what-the-model-sees.

---

## M2 — Seller accounts + storefront  `branch: m2-accounts`

*Goal: a seller signs up, connects TikTok once, and owns a storefront.*

- [x] **2.1 Auth** — `Account` model (email/phone unique) + Argon2id hashing +
      signed JWT (SECRET_KEY required). Routes: signup/login/me (anti-enumeration,
      hash never leaked, 422 border validation). Frontend: /signup + /login,
      token in lib/auth.ts, dashboard gated. 34 tests; 66 green. Live-verified. (#14)
      *You learned:* Argon2id, JWT auth, DB uniqueness, anti-enumeration,
      border validation, gating a Next.js page.
- [x] **2.2 Connect TikTok** — Seller now belongs to an Account (1-1) +
      follower_count. `services/storefront.py`: connect scrapes ONCE → auto-fills
      profile (name/avatar/bio/followers, phone from signup) AND pulls videos
      into drafts; unique-handle slug; conflict if a username is owned elsewhere.
      New endpoints: connect-tiktok / storefront / products/mine / products/refresh.
      Live-verified (connect kinjobales → 1.4M followers, 8 drafts).
      *You learned:* reusing the scraper behind an account; profile hydration.
- [x] **2.3 Storefront ownership** — every product endpoint now requires login
      and is scoped to the caller's storefront (ownership check → others'
      products read as not-found). Public `/[handle]` belongs to the account;
      phone (for M-Pesa) carried from signup. Redesigned dashboard: connect
      screen ↔ storefront profile header + product grid (screenshotted). 20
      tests; 72 green.
      *You learned:* authorization (ownership) vs authentication, account-scoping
      every query, tying public identity (handle) to a private account.

**Done when:** a seller creates an account, connects their TikTok, and their
`/[handle]` storefront shows their auto-filled profile. ✅ MET 2026-07-26 —
proven live end to end + dashboard screenshotted.

---

## M3 — Content Inbox + auto-drafting  `branch: m3-inbox`

*Goal: new TikTok content surfaces automatically as draft products to confirm.*

- [ ] **3.1 Inbox model + sync** — background/periodic scrape of the connected
      account into a Content Inbox; the manual paste box moves behind the scenes.
      *You learn:* scheduled jobs, dedupe/idempotency at scale, cost pacing.
- [ ] **3.2 🤖 Auto-detect + suggest** — run the (M1.6) agent on inbox items:
      products get name/description + price suggestion; non-products get flagged
      and filtered. Seller confirms price + stock → publish.
      *You learn:* human-in-the-loop triage, batching agent calls under a cap.

**Done when:** connecting an account fills an inbox; the seller confirms a couple
of items into published products without ever pasting a URL.

---

## M4 — Payment rails (M-Pesa)  `branch: m4-mpesa`  *(the "code transacts" layer)*

*Goal: an STK payment completes and marks an order paid — driven by plain code,
proven BEFORE any agent can call it.*

- [ ] **4.1 Order + Consent models** — state machine `pending → paid → …`; phone
      captured in Kenyan format; consent as explicit data.
- [ ] **4.2 Daraja client** — `services/mpesa.py`: OAuth, STK push, query.
- [ ] **4.3 Callback webhook** — `api/daraja.py`: verify, **idempotent** (Daraja
      retries), callback = payment truth → order `paid` → stock decrements.
- [ ] **4.4 Tunnel + sandbox test** — trigger STK with a plain button first; prove
      the whole path end to end with a sandbox number.
      *You learn:* OAuth flow, webhooks, idempotency, "callback = truth" — and why
      we build this rail fully before the agent is allowed near it.

**Done when:** a sandbox STK payment (triggered by a button, no agent yet)
completes and flips an order to paid + stock to SOLD, hands-off.

---

## M5 — 🤖 Context-aware AI sales agent  `branch: m5-agent-checkout`  *(the crown jewel)*

*Goal (seller's vision, 2026-07-26): **Video → AI Sales Agent → Catalogue → Checkout.**
A buyer taps the link FROM A SPECIFIC VIDEO and lands in a conversation that already
knows which product they came from — the WhatsApp close, on-page, minus Meta.*

The public page becomes a conversational storefront:

```
buyer taps  sokolink/<handle>?v=<video_id>
      │
      ▼
┌───────────────────────────────┐
│  👗 Product from the video     │  ← hero: the exact item, image, price, [Buy Now]
│  Black Bodycon Dress · KES 1500│
├───────────────────────────────┤
│  🤖 "Hi! You're looking at the │  ← agent already knows the video → product,
│      black dress from the video"│     price, sizes, colours, stock
│  "Do you have this in red?"     │
│  "Something similar under 1000?"│
│  [ Browse all products 🛍️ ]     │  ← catalogue as a bottom-sheet / pop-up
└───────────────────────────────┘
```

- [x] **5.0 Per-video context links** — `?v=<video_id>` features the
      product-from-video (hero); catalogue is a bottom-sheet. ProductPublicOut
      exposes `tiktok_video_id` for the match. Live-proven.
- [x] **5.1 Chat agent (Claude)** — `agent/sales.py`: claude-haiku-4-5 answers
      buyer questions grounded ONLY in the shop's published catalogue (direct
      context injection, not RAG); public `POST /api/pages/{handle}/chat`,
      input-capped. `ShopExperience.tsx`: hero + AI chat (contextual greeting,
      Sheng-aware) + bottom-sheet. Live: answered a real buyer Q in context.
      (Built before M4 per Fredrick — the chat touches no money.) TOOLS
      (`create_order`, `send_stk_push`) come with 5.2 after M4.
      *You learned:* context injection vs RAG, a grounded chat agent, per-video
      deep-linking, bottom-sheet UX.
- [ ] **5.2 Close the sale** — agent confirms item + collects phone → calls
      `send_stk_push` (the M4 rail) → M4 callback = truth marks it paid. The agent
      never charges; it *requests* a charge the rails execute.
      *You learn:* agent-proposes/code-disposes across a real payment.

**Done when:** a buyer taps a video link, chats to find/confirm a product, and
completes a sandbox purchase entirely on-page. **Needs M4 rails first** (rails
before agent) and **Gemini/LLM billing** enabled.

---

## M6 — Seller ↔ customer chat  `branch: m6-seller-chat`

*Goal: the seller can step into the conversation.*

- [ ] **6.1 Handoff + notify** — seller gets pinged when a buyer needs them; can
      reply. Async first (notification + reply), live (websockets) later.
      *You learn:* real-time transport, human-in-the-loop handoff.

**Done when:** a seller answers a buyer's question inside the SokoLink chat.

---

## M7 — Reach + pilot  `branch: m7-pilot`

*Goal: retention SMS + go live with a real seller.*

- [ ] **7.1 Reach (SMS)** — consent registry + STOP; paced restock broadcasts;
      🤖 agent drafts the message (seller approves), timing logic decides when.
- [ ] **7.2 Hardening + deploy** — logging, rate limits, secrets audit; frontend
      to Vercel, backend + Postgres + Redis to a VPS; real credentials.
- [ ] **7.3 Pilot** — one real seller, one real order, end to end.

**Done when:** money moves for real and nothing was touched by hand.

---

## M8 — Seller analytics & insights  `branch: m8-analytics`  *(planned — seller ask 2026-07-26)*

*Goal: a simple seller dashboard with three places — **Products**, **Analytics**,
**Customers** — that answer "how are my videos doing?" and "what do people
actually want?" Kept deliberately lean (not the busy reference dashboard).*

**What data we ACTUALLY have (verified against the raw Apify payload, `spikes/out/raw_item_00.json`):**

| Seller wants | Reality | Source |
|---|---|---|
| Traction per video (views) | ✅ in the scrape, just not stored | `playCount` (e.g. 1718) |
| Number of comments per video | ✅ in the scrape, just not stored | `commentCount` (also `diggCount` likes, `shareCount`, `collectCount` saves) |
| **What people are asking for** | ⚠️ must instrument — richer from OUR chat than TikTok | persist sales-chat questions (goldmine); OR pay for TikTok comment TEXT (`commentsPerPost>0`, costs more) |
| Clicks on the SokoLink link / asked directly | ⚠️ must instrument (only WE can see this) | log page views, `?v=` opens, paste-link resolves, chat opens |
| Shop location in Nairobi (for directions) | ❌ TikTok has NO structured location | **seller-entered** profile field; AI can pre-fill from the bio (`signature` holds addresses — spike 00) |

**Phase A — start the data flywheel (do EARLY, cheap, no UI). "When the data comes we're ready" means capturing NOW so history exists to show later:**
- [ ] **8.1 Capture video metrics** — widen `TikTokVideo` schema + add `views/likes/comments/shares/saves` columns on `Product` (migration); store on every scrape. Zero extra Apify cost (already in the payload).
- [ ] **8.2 Event log** — a lightweight `Event` table: `page_view`, `video_open` (`?v=`), `link_resolve` (paste), `chat_open`, `chat_query`. Fire-and-forget from the public routes.
- [ ] **8.3 Persist buyer questions** — log each sales-chat user message (shop, video, text, ts). This is the "what people want" goldmine — our own data, richer than TikTok comments.
- [ ] **8.4 Shop location + hours** — seller-entered fields on the storefront profile (independently shippable; also feeds M4 checkout directions). Optional AI pre-fill from bio.

**Phase B — surface it (when there's data worth showing):**
- [ ] **8.5 Analytics tab** — per-video traction (views/likes/comments), SokoLink link clicks, # chats, **top asked-for products** + demand for sold-out items (restock signal).
- [ ] **8.6 Customers tab** — who engaged (from chats/orders once M4 lands) + a "what people are asking" digest.

**Optional:** fetch TikTok comment TEXT (`commentsPerPost>0`) to mine questions from the comments themselves — only if chat-question mining isn't enough (has per-scrape cost).

*You learn:* an analytics event pipeline, aggregation queries, and the product
lesson that **the most valuable data is the data you instrument yourself** (the
chat), not what the platform hands you.

**Done when:** a seller can open Analytics and see real numbers for her own videos
and a ranked list of what buyers keep asking for.

---

## The agentic learning arc (where the 🤖 lives)

| Session | Agent concept |
|---------|---------------|
| 1.2 Scraper draft | LLM as **structured extractor**: image → validated draft |
| 1.6 Smart drafting | LLM **reads a price it can see** but only *suggests* it — guardrail precision |
| 3.2 Inbox triage | LLM as **filter + proposer** over a stream, human confirms |
| 5.1–5.2 Checkout | LLM as **tool user** driving a real payment — proposes the STK, rails execute |
| 7.1 Reach | LLM as **proposer with guardrails**: drafts + timing, human approves |
| Spine (M4) | Why agents need **deterministic rails** built first: state machines, idempotency, "callback = truth" |

The honest lesson of this build: an "agentic system" is ~20% LLM calls and ~80%
rails that make those calls safe, observable, and reversible. We build the rails
first on purpose.

---

## Status log

| Date | What happened |
|------|---------------|
| 2026-07-22 | Repo initialized, first commit pushed to `Data-Amigo/PROJECT_TIKTOK`; workplan written |
| 2026-07-22 | Data decision: Apify actor as scrape engine (key acquired); Display API later, oEmbed as edge fallback. Quality bar set: production-grade POC |
| 2026-07-22 | Spike 00 done on real seller data. Key insight: captions have NO product info → product draft comes from cover image (vision LLM), not caption parsing. Bio = auto-fill onboarding data |
| 2026-07-23 | GitHub issue log live (milestone M0, issues #1–#5). Branding renamed TIKTOK. Session 0.4 wired frontend↔backend↔DB — **M0 done-when met**, merged to main |
| 2026-07-24 | M1.2 scraper (Apify adapter, validation border) + 🤖 draft agent. Model decision: **Gemini (gemini-3.6-flash) for vision** — reads Sheng/Swahili better than Anthropic (tested); Anthropic reserved for conversation. Live proof: hashtag-only cover → clean product draft, Sheng text translated, no price/stock (guardrail held) |
| 2026-07-25 | M1.3 Products API — ingest/autofill/patch/public-page across schemas/service/routes; drafting split to on-demand (cost rail); 9 tests, 32 green (#11). CONCEPTS.md added (why-not-RAG etc.); Phase 2 generative try-on recorded |
| 2026-07-25 | M1.4 Dashboard UI — Next.js seller screen (paste→ingest→autofill→price→publish), /media static mount. Live proof: real kinjobales ingest → Gemini named "Sundabests Insulated Beverage Dispenser" off the cover → published → public page (#12) |
| 2026-07-25 | M1.5 Public SokoLink Page — server-rendered sokolink/<handle>, OG previews, 404+error boundaries, mobile-first, honest checkout-coming CTA. Screenshotted live. **M1 done-when met** → merge to main (#13) |
| 2026-07-25 | **Roadmap pivot** (seller feedback): account-first shop ending in an on-page **agentic checkout** (WhatsApp close relocated to web; M-Pesa thesis kept). Milestones re-sequenced M2 accounts → M3 inbox → M4 M-Pesa rails → M5 agent checkout → M6 seller chat → M7 reach+pilot |
| 2026-07-25 | M1.6 Smart drafting — agent reads printed price (suggested_price_kes, pre-fills box, seller confirms) + product/non-product flag. Fixes real complaint. Live: clog covers → KES 600/650/900 read correctly. Guardrail refined in CONCEPTS §4. 35 tests green |
| 2026-07-25 | Hotfix: friendly 429 when Gemini free-tier daily cap (20/day) hits — seller-safe message, not raw JSON. Guidance: enable Gemini billing for customer testing |
| 2026-07-25 | M2.1 Seller accounts — Argon2id + JWT auth (signup/login/me), Kenyan phone normalization, browser sign-in (signup/login pages, gated dashboard). 34 tests, 66 green, live-verified (#14). SECRET_KEY added to .env |
| 2026-07-25 | Rebrand: BOB → **SokoLink**, slogan "Where your audience becomes your customers." (23 files, verified live) |
| 2026-07-26 | M2.2/2.3 Connect TikTok + account-scoped storefront — Seller↔Account 1-1, connect auto-fills profile + pulls videos, product endpoints login-gated + ownership-checked, redesigned dashboard (connect ↔ storefront). 72 green, live end to end. **M2 done-when met** → merge to main |
| 2026-07-26 | **Auto-drafting** (seller feedback: "don't make me click auto-fill"). Products auto-draft on connect/refresh (name/desc + a readable price → DRAFT price; publish stays the human gate — guardrail v3, CONCEPTS §4). Graceful AI-cap pause + manual fallback. Auth tests randomized (collision-proof). 75 green. **Gemini billing is the gate for auto-draft + the M5 agent.** M5 reshaped into the context-aware AI sales agent (Video→Agent→Catalogue→Checkout, per-video `?v=` links, bottom-sheet catalogue) per seller's vision |
| 2026-07-26 | M5.1 AI sales chat live (context injection, not RAG) — human persona (shop avatar/name, no bot badge), grounded rails (no invented colour/size/stock, sold-out honesty, Sheng comprehension). M5.2 paste-a-TikTok-link → feature the product (TikTok gives no per-video link/referrer; SSRF-guarded short-link resolve). Provider swung Anthropic→OpenAI→**Gemini** (paid, best at Swahili/Sheng) through the one-file agent seam. 91 green |
| 2026-07-26 | **M8 planned** (seller ask): analytics + customers tabs. Verified against raw Apify payload — views/likes/**comment count** are in the scrape (not yet stored); location is NOT (seller-entered, AI-prefill from bio); "what people ask for" + link clicks must be **instrumented** (persist chat questions + event log). Decision: **start capturing early** (Phase A flywheel) so data exists when we build the views (Phase B) |
