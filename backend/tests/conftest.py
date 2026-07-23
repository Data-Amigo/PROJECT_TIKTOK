"""
Shared test fixtures. (Note: the OTHER conftest.py at backend/ root exists
only to put backend/ on sys.path — this one holds actual fixtures.)
"""

import pytest
from sqlalchemy.orm import Session

from app.db import engine


@pytest.fixture
def db_session():
    """A session inside a transaction that is ALWAYS rolled back.

    The pattern:
        connect ──> BEGIN ──> test does whatever it wants ──> ROLLBACK

    Every INSERT/UPDATE the test performs is real (real Postgres, real
    constraints — that's the point: SQLite couldn't check our JSONB or the
    CHECK constraints the same way), yet none of it survives the test.
    The database is left exactly as found, every run, pass or fail.
    """
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn)
    try:
        yield session
    finally:
        session.close()
        trans.rollback()   # the always-undo: nothing a test writes persists
        conn.close()
