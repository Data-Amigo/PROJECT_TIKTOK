# WORKPLAN — Project TICKTOCK (BOB for Commerce)

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
│  BOB Page   │ ◄────────── │  FastAPI backend          │
│ (Next.js)   │             │  api/ agent/ services/    │
│ bob.link/x  │             │  models/ ── Postgres      │
└─────┬───────┘             └────┬─────────────┬───────┘
      │ buyer fills order form   │             │
      ▼                          ▼             ▼
┌─────────────┐   STK push   ┌───────┐   ┌────────────┐
│ BOB Checkout│ ───────────► │Daraja │   │ Africa's   │
│ name·phone· │ ◄─────────── │M-Pesa │   │ Talking SMS│
│ consent     │   callback   └───────┘   └─────┬──────┘
└─────────────┘  = payment truth               │
                                               ▼
                                    BOB Reach: restock SMS
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

- [ ] **0.0 Data spike** — standalone script: real Kenyan seller's TikTok →
      Apify actor run → inspect the JSON we actually get (captions, covers,
      prices-in-captions?) → download a thumbnail to disk. Findings shape the
      `Product` model in 1.1.
      *You learn:* Apify's actor/run/dataset model; letting real data drive the
      schema instead of guessing.
- [ ] **0.1 Backend skeleton** — Python venv, FastAPI app (`main.py`, `config.py`),
      `/health` endpoint, `requirements.txt`.
      *You learn:* FastAPI app anatomy, why config lives in env vars (12-factor).
- [ ] **0.2 Database layer** — `docker-compose.yml` (Postgres + Redis), `db.py`
      (SQLAlchemy engine + session), Alembic init + first empty migration.
      *You learn:* why migrations exist, the engine/session pattern, what Redis
      will be for later (idempotency, pacing).
- [ ] **0.3 Frontend skeleton** — Next.js (TypeScript + Tailwind) app, hello page.
      *You learn:* App Router layout, where `[handle]` dynamic routes fit.
- [ ] **0.4 Wire-up** — frontend calls backend `/health` and shows the status;
      `.env.example` listing every key the app will ever need.
      *You learn:* CORS, the frontend↔backend contract, secret hygiene.

**Done when:** `docker compose up` + uvicorn + `npm run dev` all boot and the
frontend shows the backend is healthy.

---

## M1 — BOB Page  `branch: m1-bob-page`

*Goal: seller creates a page; public link shows item, price, Available/SOLD.*

- [ ] **1.1 Models** — `Seller` and `Product` tables + Alembic migration.
      *You learn:* SQLAlchemy models, relationships, migration workflow for real.
- [ ] **1.2 🤖 Scraper service** — `services/scraper.py`: Apify engine behind our
      own interface (`fetch_video`, `fetch_profile`) → caption, cover, metadata;
      thumbnails stored by us. First agentic piece: an LLM turns a messy caption
      into a structured product draft (name, description, suggested tags) —
      the seller confirms; the LLM never sets price/stock.
      *You learn:* tool-building for agents, structured output, why we validate
      LLM output with schemas instead of trusting it.
- [ ] **1.3 Products API** — `api/products.py`: create-from-link, set price/stock,
      get-by-handle. Tests with pytest.
      *You learn:* Pydantic request/response schemas, the service→route split,
      first real tests.
- [ ] **1.4 Dashboard UI** — paste link → preview draft → set price + stock → publish.
      *You learn:* calling the API from Next.js, shared types in `shared/schemas/`.
- [ ] **1.5 Public page** — `[handle]/page.tsx`: today's drop, live
      Available/SOLD badge.
      *You learn:* server components, dynamic routes, why the public page reads
      stock from the DB (single source of truth) not from the scrape.

**Done when:** a seller pastes a real TikTok link and a public `bob.link/handle`
page shows the item with live availability.

---

## M2 — Checkout + contact capture  `branch: m2-checkout`

*Goal: submitting the order form creates an order row with the phone captured.*

- [ ] **2.1 Models** — `Order` (name·phone·item·amount·status·time) and `Consent`
      tables + migration. Order status is a small state machine:
      `pending → paid → packed → delivered` (+ `failed`).
      *You learn:* modelling a state machine in a DB; why status transitions are
      code, not vibes.
- [ ] **2.2 Orders API** — create order, list orders for seller, validate phone
      (Kenyan format 2547XXXXXXXX), consent checkbox captured explicitly.
      *You learn:* input validation as a security boundary; consent as data.
- [ ] **2.3 Checkout UI** — on-page order form (name, phone, delivery, consent),
      optimistic UX, error states.
      *You learn:* forms that fail gracefully; why the phone field is the
      whole business model (payment = contact capture).

**Done when:** submitting the form creates an order row you can see in the
dashboard, with phone + consent recorded.

---

## M3 — M-Pesa close  `branch: m3-mpesa`

*Goal: sandbox STK payment completes; order paid; stock auto-updates.*

- [ ] **3.1 Daraja client** — `services/mpesa.py`: OAuth token, STK push, query.
      Sandbox credentials in `.env`.
      *You learn:* OAuth client-credentials flow, signing requests, sandbox vs prod.
- [ ] **3.2 Callback webhook** — `api/daraja.py`: receive the callback, verify,
      **idempotency via Redis** (Daraja can retry — we must not double-fulfil).
      *You learn:* webhooks, idempotency keys, why "callback = payment truth".
- [ ] **3.3 Order flow wiring** — checkout submit → STK push to buyer's phone →
      callback flips order `pending → paid` → stock decrements → page shows SOLD.
      *You learn:* an end-to-end async flow across four systems.
- [ ] **3.4 Tunnel + live sandbox test** — ngrok/cloudflared so Daraja can reach
      localhost; full test with a sandbox number.
      *You learn:* exposing localhost safely, reading Daraja's (weird) callback JSON.

**Done when:** a sandbox payment completes end to end and the public page flips
to SOLD without anyone touching the DB.

---

## M4 — Fulfilment + SMS confirm  `branch: m4-fulfilment`

*Goal: seller sees packed-order card; buyer gets SMS confirmation + rider details.*

- [ ] **4.1 SMS service** — `services/sms.py`: Africa's Talking client behind our
      own interface (so WhatsApp can swap in later without touching callers).
      *You learn:* the adapter pattern — the single most important design habit
      in this repo.
- [ ] **4.2 Buyer confirmation** — on `paid`, send SMS receipt; on `packed`,
      send rider details. Every send is audit-logged.
      *You learn:* event-driven side effects, audit trails.
- [ ] **4.3 Seller fulfilment UI** — packed-order card in dashboard; mark packed /
      delivered; status history visible.
      *You learn:* driving the state machine from the UI.

**Done when:** after a sandbox payment, the seller gets a packed card and the
buyer's phone gets a real SMS with rider details.

---

## M5 — BOB Reach  `branch: m5-reach`

*Goal: opted-in buyer gets a restock SMS; STOP removes them.*

- [ ] **5.1 Consent registry + STOP** — inbound SMS webhook; STOP instantly flips
      consent off; audit-logged.
      *You learn:* compliance as a feature; two-way SMS.
- [ ] **5.2 Broadcast worker** — Redis-backed queue; paced sends with jittered
      delays and rate limits; dry-run mode first.
      *You learn:* background workers, pacing/backoff — the ops side of agents.
- [ ] **5.3 🤖 Reach agent** — the LLM drafts the restock message per product
      (seller approves), and timing logic decides *when* to send (not 2am).
      Guardrails: opt-in only, caps per day, STOP always wins.
      *You learn:* agent guardrails, human-in-the-loop approval, why the agent
      proposes and code disposes.

**Done when:** an opted-in test number receives a restock SMS from a broadcast;
replying STOP removes it and the next broadcast skips it.

---

## M6 — Pilot-ready  `branch: m6-pilot`

*Goal: live on real credentials; a real seller runs one full order end to end.*

- [ ] **6.1 Seller auth** — login for the dashboard (simple, boring, safe).
- [ ] **6.2 Hardening** — error handling, request logging, rate limits on public
      endpoints, secrets audit.
- [ ] **6.3 Deploy** — frontend to Vercel; backend + Postgres + Redis to a VPS;
      real Daraja + Africa's Talking credentials.
- [ ] **6.4 Pilot** — one real seller, one real order, end to end. Watch the logs.

**Done when:** money moves for real and nothing was touched by hand.

---

## The agentic learning arc (where the 🤖 lives)

| Session | Agent concept |
|---------|---------------|
| 1.2 Scraper | LLM as a **tool user**: unstructured caption → validated structured draft |
| 5.3 Reach | LLM as a **proposer with guardrails**: drafts + timing, human approves, code enforces limits |
| M2–M4 spine | Why agents need **deterministic rails**: state machines, idempotency, audit logs |
| Future | Product Q&A agent on the BOB Page; WhatsApp channel swap behind `services/` |

The honest lesson of this build: an "agentic system" is ~20% LLM calls and ~80%
rails that make those calls safe, observable, and reversible. We build the rails
first on purpose.

---

## Status log

| Date | What happened |
|------|---------------|
| 2026-07-22 | Repo initialized, first commit pushed to `Data-Amigo/PROJECT_TIKTOK`; workplan written |
| 2026-07-22 | Data decision: Apify actor as scrape engine (key acquired); Display API later, oEmbed as edge fallback. Quality bar set: production-grade POC |
