from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# ── OUR WIRING ────────────────────────────────────────────────────────────────
# Alembic runs from backend/, same as uvicorn — make `app` importable, then
# reuse the ONE config and the ONE metadata the app itself uses. If this file
# had its own copy of the DB URL, the app and its migrations could disagree
# about which database is "the" database. Never two sources of truth.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> backend/

from app.config import settings
from app.db import Base

# Import models so their tables register on Base.metadata BEFORE autogenerate
# diffs it against the live DB. A model that isn't imported here is INVISIBLE
# to Alembic — it would generate a migration that DROPS the "unknown" table.
from app import models  # noqa: F401  (imported for its side effect: registration)

config = context.config

# Feed the URL from settings into Alembic's config (overrides alembic.ini,
# where we deliberately leave the URL blank — secrets never live in .ini
# files because those get committed).
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# What the schema SHOULD look like — autogenerate diffs this vs the live DB.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
