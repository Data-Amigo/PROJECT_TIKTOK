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
