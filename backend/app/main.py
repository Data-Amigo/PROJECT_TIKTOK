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

from app.config import settings

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
    """Liveness: is the process up and its config loaded? Always cheap.

    Deliberately does NOT touch Postgres/Redis — liveness and readiness are
    different questions. If health depended on the DB, a DB blip would make
    the platform restart a perfectly fine process (a restart cannot fix a
    down database). Instead, the `checks` map grows a real dependency report
    in 0.2, so a tester's bug report names the dependency that died.
    """
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
        "checks": {
            "api": "ok",
            # "db": …      arrives in session 0.2
            # "redis": …   arrives in session 0.2
        },
    }
