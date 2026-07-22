# Project TICKTOCK — BOB for Commerce

An AI agent that turns a TikTok/Instagram post into a complete sale — **post once, sell everywhere.**

> **Scope:** Commerce only. Insurance is a separate, later effort.
> **v1 is web-first:** no WhatsApp yet (too easily blocked, and we're skipping the Meta
> application for now). The customer orders on a web page and pays with M-Pesa; BOB
> follows up by SMS. WhatsApp is a later upgrade using the same consented contact list.

**Stack:** FastAPI (Python) backend · Next.js frontend · **M-Pesa Daraja** (payments) · **Africa's Talking** (SMS).

---

## How a sale works (v1, web-first)

```
Discover        Browse            Order + contact        Pay              Fulfil + confirm
TikTok/IG   →   BOB Page shows →  on-page form:      →   STK push to  →   seller sees order,
post,           today's drop      name · phone ·         that phone,      buyer gets SMS
tap the link    + availability    delivery · consent     Daraja = truth   + rider details
```

**The key idea:** M-Pesa's STK push is sent *to a phone number*, so the checkout form has to
collect the phone to charge them — and that same number **is** the customer's contact.
Payment and contact capture are one step. Every order becomes a clean row:
`name · phone · item · amount · time · consent`.

**Retention:** opted-in numbers get restock/offer alerts by **SMS** (Africa's Talking). No Meta needed.

---

## The three pieces

| Piece | v1 (web-first) |
|-------|----------------|
| **BOB Page** | AI link-in-bio. Seller pastes a TikTok/IG link → BOB pulls video, caption, thumbnail → seller adds price + stock. Buyers see today's drop with live availability. |
| **BOB Checkout** | On-page order form captures name, phone, delivery + consent, then fires the M-Pesa STK push. Replaces the WhatsApp close. |
| **BOB Reach** | Consent-based **SMS** marketing. Opt-in at checkout, paced restock broadcasts, STOP handling. |

---

## Folder map

```
Project TICKTOCK/
├─ frontend/          Next.js — the BOB Page + seller dashboard + checkout form
│  ├─ app/
│  │  ├─ [handle]/    public page: bob.link/mama-wanjiku
│  │  ├─ dashboard/   seller: paste link, set price & stock, see orders
│  │  └─ api/         light routes that call the backend
│  ├─ components/     reusable UI (product card, order form, order button)
│  ├─ lib/            api client + shared TS types
│  └─ public/         static assets
│
├─ backend/           FastAPI — the brain: products, orders, payments, SMS
│  ├─ app/
│  │  ├─ api/         HTTP endpoints (products, orders, daraja, reach)
│  │  ├─ agent/       link parsing, product Q&A, Reach timing (the AI parts)
│  │  ├─ services/    external clients (scraper, M-Pesa, Africa's Talking SMS)
│  │  └─ models/      database tables (seller, product, order, consent)
│  ├─ alembic/        database migrations
│  └─ tests/
│
├─ shared/schemas/    request/response contracts shared by both apps
└─ docs/              technical flow + notes
```

**The habit:** for any feature, build the backend first
(`model → migration → service → API route → test`), then wire the Next.js UI to it.

---

## Milestones (one at a time — don't skip ahead)

| # | Goal | Done when |
|---|------|-----------|
| **M0** | Foundation | All services boot; `/health` returns 200 |
| **M1** | BOB Page | Seller makes a page; public link shows item, price, availability |
| **M2** | Checkout + contact | Submitting the order form creates an order row with the customer's phone captured |
| **M3** | M-Pesa close | Sandbox STK payment completes; order paid; stock auto-updates |
| **M4** | Fulfilment + SMS | Seller sees a packed-order card; buyer gets an SMS confirmation + rider details |
| **M5** | BOB Reach (SMS) | Opted-in buyer gets a restock SMS; STOP removes them |
| **M6** | Pilot-ready | Live on real credentials; a real seller runs one full order end to end |

See `docs/` for the full technical flow.

---

## Future upgrade: WhatsApp

Once there's traction and Meta Business verification is done, add a WhatsApp channel
behind the same `services/` interface and upgrade the consented contact list from SMS to
WhatsApp. Nothing built here is wasted.

---

## Status

- [x] Folder skeleton
- [x] Plan set to web-first
- [ ] M0 — Foundation (in progress)
