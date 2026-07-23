"""
Tests for /health — the first test in the repo, so it also documents the habit:

    every API behaviour we claim, a test proves. Run from backend/:
        .venv/Scripts/python -m pytest tests/ -v

TestClient runs the FastAPI app IN-PROCESS (no server, no port, no network) —
this is why API tests stay fast enough to run on every commit.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200_and_ok_status():
    """The one promise M0 makes: the app boots and answers."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_health_reports_its_checks():
    """The checks map is the contract testers rely on to name a dead
    dependency — make sure it exists and the api itself reports ok."""
    body = client.get("/health").json()
    assert body["checks"]["api"] == "ok"


def test_cors_allows_the_frontend_origin():
    """A browser at localhost:3000 must be allowed to read our responses.
    The middleware only emits the header when the request CARRIES an Origin —
    that's why the test sends one (a plain curl never sees CORS headers)."""
    resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_rejects_unknown_origins():
    """An arbitrary website must NOT get the allow header — its visitors'
    browsers will then refuse to hand it our responses."""
    resp = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers


def test_health_reports_db_readiness():
    """DB check present and ok. NOTE: this test does a real round-trip to
    Railway (~200ms) — acceptable while the suite is small; if it ever gets
    annoying, this is the first test to move behind a marker."""
    body = client.get("/health").json()
    assert body["checks"]["db"] == "ok"
    assert body["status"] == "ok"
