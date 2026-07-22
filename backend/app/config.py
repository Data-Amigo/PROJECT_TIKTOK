"""
Config — single source of truth for every setting the backend needs.

    .env (project root) ──> pydantic Settings ──> validated, typed object
                                                   imported everywhere as
                                                   `from app.config import settings`

Why this exists (vs os.getenv sprinkled around):
    1. TYPED   — a missing/malformed key fails loudly AT STARTUP, not at 2am
                 in the middle of a buyer's checkout.
    2. CENTRAL — every setting lives here; grep this one file to know what
                 the app depends on. .env.example mirrors it.
    3. ONE READ — validated once at import; the rest of the app just uses it.

Rule: no other module reads os.environ or .env directly. Ever.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ── PATHS ─────────────────────────────────────────────────────────────────────
# backend/app/config.py -> parents[2] = project root ("Project TICKTOCK/").
# The .env lives at PROJECT ROOT (not backend/) because frontend tooling and
# docker-compose will read from the same file — one .env for the whole repo.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Everything configurable, with safe dev defaults where safe defaults exist.

    Fields WITHOUT a default (none yet — DATABASE_URL joins them in 0.2 once
    Postgres is real) are REQUIRED: the app refuses to boot if they're absent.
    That refusal is a feature — better a dead process than a half-working one.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",   # emojis taught us: UTF-8 everywhere, always
        extra="ignore",              # unknown keys in .env don't crash the app —
                                     # lets .env carry frontend-only vars too
    )

    # ── App identity ──
    app_name: str = "BOB for Commerce"
    app_env: str = "dev"             # dev | staging | prod — gates docs page etc.

    # ── External services ──
    # Empty-string default (not required) because M0 must boot on a fresh
    # clone with zero keys; the scraper service (M1.2) checks it at CALL time
    # and fails with a human message, same pattern as the spike.
    apify_api_token: str = ""

    # Placeholder until 0.2 makes Postgres real — then it loses its default
    # and becomes required.
    database_url: str = ""


# The one instance the whole app shares. Import THIS, never instantiate again —
# re-instantiating would re-read .env and could disagree mid-flight.
settings = Settings()
