"""
App entry — builds the FastAPI app and registers every router.

    uvicorn app.main:app --reload          (run from backend/)

    request ──> FastAPI app ──> router (api/…) ──> service (services/…) ──> DB
                     │
                     └── /health  answered right here (no router needed yet)

This file stays THIN on purpose: it wires things together and owns nothing
else. Business logic lives in services/, HTTP shapes live in api/ — when a
file in here grows past ~100 lines, something is in the wrong place.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.db import engine

# ── APP ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    # The interactive /docs page is a gift in dev and a liability in prod
    # (it advertises your whole API surface). Gate it on environment now so
    # nobody has to remember later.
    docs_url="/docs" if settings.app_env == "dev" else None,
    redoc_url=None,  # one docs UI is enough
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Lets pages served from our frontend origin call this API FROM THE BROWSER
# (dashboard forms, checkout). Server-side fetches (Next.js server components)
# never hit this — CORS is purely a browser-enforced rule. Origins come from
# config; wildcard is forbidden there, see config.py for the why.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],   # fine to be broad once the ORIGIN is locked down
    allow_headers=["*"],
)


# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health() -> dict:
    """Process liveness + dependency readiness, in one honest report.

    The liveness/readiness split, kept: this endpoint ALWAYS answers 200 —
    a down database must not make the platform restart a fine process (a
    restart can't fix Postgres). Instead `status` flips to "degraded" and
    `checks` names the dead dependency, so a tester's bug report says
    "db: down" instead of "it's broken".
    """
    checks = {"api": "ok"}

    # DB readiness: cheapest possible round-trip (SELECT 1). pool_pre_ping +
    # the 10s connect timeout in db.py bound how long this can take.
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:
        # Deliberately broad: ANY failure mode (DNS, auth, timeout, Railway
        # asleep) reports the same way. Detail goes in logs, not to strangers.
        checks["db"] = "down"

    # checks["redis"] joins in M3, when Redis actually exists.

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "service": settings.app_name,
        "env": settings.app_env,
        "checks": checks,
    }
