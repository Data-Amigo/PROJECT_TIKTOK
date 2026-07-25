# Why this file exists: pytest walks UP from a test file until it finds a
# conftest.py, and adds THAT directory to sys.path. This makes `backend/`
# importable, so tests can do `from app.main import app` exactly like uvicorn.
#
# It also holds shared fixtures. The key one is `db_session`: a database
# session wrapped in a transaction that is ROLLED BACK when the test ends —
# so tests exercise the real Postgres (real constraints, real types like
# JSONB) while writing nothing permanent. This is why we can test against the
# live Railway dev DB without polluting it.

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine, get_db
from app.main import app


@pytest.fixture
def db_session():
    """A transactional session that rolls back everything on teardown.

    join_transaction_mode="create_savepoint": even the service's own
    db.commit() calls land in a SAVEPOINT inside our outer transaction, so the
    single rollback below still erases them. Nothing survives the test.
    """
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()   # discard everything the test wrote
        connection.close()


@pytest.fixture
def client(db_session):
    """A TestClient whose requests use the rolled-back db_session, so an API
    call and the test assertions see the SAME uncommitted data."""
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()  # don't leak the override to other tests
