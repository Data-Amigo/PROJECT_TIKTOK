"""
Database layer — SQLAlchemy engine, session factory, and the model base class.

    request ──> get_db() ──> Session (one per request, auto-closed)
                                │
                             engine (ONE per app) ──> connection pool ──> Railway

The mental model:
    ENGINE   = the app's phone line to Postgres. Created once at import.
               Owns a pool of live connections because opening one is slow
               (TCP + TLS + auth ≈ 100ms to Railway — you don't pay that per
               request, you reuse).
    SESSION  = one request's private workspace. Cheap to make, lives for one
               request, then closed NO MATTER WHAT. All uncommitted changes
               die with it — which is exactly the safety you want.

Rule: routes/services never touch `engine` directly — they receive a session
via the get_db dependency. That keeps transactions request-scoped and testable.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# ── ENGINE ────────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.sqlalchemy_database_url,
    # THE cloud-Postgres fix: Railway silently drops idle connections. Without
    # this, the pool hands you a corpse and the request dies with a cryptic
    # "server closed the connection unexpectedly" — but only after the app has
    # been quiet for a while, i.e. the hardest kind of bug to reproduce.
    # pre_ping tests each connection with a no-op before lending it out.
    pool_pre_ping=True,
    # Recycle connections older than 5 min — belt AND suspenders against the
    # same silent-drop behaviour (pre_ping catches dead ones; recycle stops
    # them getting old enough to die mid-request).
    pool_recycle=300,
    # A hung connect attempt should fail in 10s, not hang a request forever.
    connect_args={"connect_timeout": 10},
)

# ── SESSION FACTORY ───────────────────────────────────────────────────────────
# autoflush=False: we decide when SQL hits the DB (explicit commit), not the
# ORM sneaking writes mid-read. Predictability > magic.
SessionLocal = sessionmaker(bind=engine, autoflush=False)


# ── MODEL BASE ────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Every table model (Seller, Product, Order…) inherits from this.

    Alembic reads Base.metadata to know what the schema SHOULD look like and
    autogenerates migrations from the diff vs what the DB actually looks like.
    """


# ── REQUEST DEPENDENCY ────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: hands each request its own session, guarantees
    close. Usage in a route:

        @router.get("/products")
        def list_products(db: Session = Depends(get_db)): ...

    The try/finally is the whole point — even if the route raises, the
    session closes and its connection returns to the pool. Leak sessions and
    the pool empties; the app then freezes waiting for a free connection
    (a classic "works fine until traffic" failure).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
