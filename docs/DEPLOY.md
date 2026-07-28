# Deploying SokoLink to Railway

This is a **monorepo** (`backend/`, `frontend/`, `docs/`, `shared/`). Railway
builds **one service per app**, each pointed at its own subfolder. The first
deploy failed because the service was pointed at the repo **root**, where there's
no `requirements.txt`/`package.json` for the builder to detect — so it couldn't
tell what to build.

## Backend service (deploy this first — M-Pesa needs it)

The repo has a root **`Dockerfile`** that builds the backend. Railway uses it
automatically, so **no Root Directory setting is needed** — the Dockerfile
installs `backend/requirements.txt`, runs `alembic upgrade head` (idempotent),
and starts `uvicorn app.main:app` on `$PORT`. (`.dockerignore` keeps `.venv`,
`media/`, and the frontend out of the build.)

1. **New service → Deploy from GitHub repo** → pick `PROJECT_TIKTOK`.
2. If the build still shows *"Railpack analyzed …"* (auto-detect) instead of
   using the Dockerfile: **Settings → Build → Builder = Dockerfile**. That's the
   only setting that might need a nudge.
3. **Variables** → add every key from your local `.env` (copy the values):

   | Variable | Notes |
   |---|---|
   | `DATABASE_URL` | the Railway Postgres URL (required — build's `alembic` step needs it) |
   | `SECRET_KEY` | required — signs JWTs |
   | `GEMINI_API_KEY` | both AI agents |
   | `APIFY_API_TOKEN` | the TikTok scraper |
   | `MPESA_CONSUMER_KEY` / `MPESA_CONSUMER_SECRET` | Daraja app |
   | `MPESA_SHORTCODE` | `174379` (sandbox) |
   | `MPESA_PASSKEY` | sandbox passkey |
   | `MPESA_ENV` | `sandbox` |
   | `MPESA_CALLBACK_URL` | **set AFTER step 4** (needs the public URL) |

4. **Settings → Networking → Generate Domain** → gives a free
   `https://<name>.up.railway.app`. That HTTPS URL is enough for the M-Pesa
   callback — Safaricom can POST to it. (A custom domain is optional, below.)
5. Set `MPESA_CALLBACK_URL` = `https://<name>.up.railway.app/api/daraja/callback`
   *(the callback endpoint is built in M4.3.)*

**Note:** Railway's filesystem is ephemeral — locally-stored cover images
(`backend/media/`) don't survive a redeploy. Re-scraping re-downloads them;
object storage (S3/R2) is the later fix (workplan M7.2).

## Frontend service (the shop UI buyers see)

A **second** Railway service in the same repo, built by `frontend/Dockerfile`
(Next.js standalone).

1. **New service → same repo** → **Settings → Source → Root Directory = `frontend`**
   (so Railway uses `frontend/Dockerfile`).
2. **Variables:**
   - `NEXT_PUBLIC_API_URL = https://projecttiktok-production.up.railway.app`
     ⚠️ This is inlined at **build** time (it's a `NEXT_PUBLIC_*` var), so it must
     be set *before* the build — the Dockerfile takes it as a build ARG.
3. **Generate Domain** → gives the frontend's public URL (e.g.
   `https://<name>.up.railway.app`) — **this is the shop link customers open.**
4. **Let the browser call the API:** on the **backend** service, add the frontend
   URL to `CORS_ORIGINS` (comma-separated), e.g.
   `CORS_ORIGINS = http://localhost:3000,https://<frontend>.up.railway.app`.
   (Server-rendered pages don't need this, but the chat/checkout/paste calls run
   in the browser and do.)

## Custom domain

Free `*.up.railway.app` works immediately. For your own domain:
1. Service → **Settings → Networking → Custom Domain** → enter e.g.
   `api.yourdomain.com` (backend) or `yourdomain.com` (frontend).
2. Railway shows a **CNAME target** → add that CNAME at your domain registrar's
   DNS. Railway auto-provisions TLS once DNS resolves.
3. If you use a custom domain for the backend, update `MPESA_CALLBACK_URL` to it.

You don't need the custom domain to test M-Pesa — the generated Railway URL is
fine. Do the domain whenever; it doesn't block the payment flow.
