# Why this (almost) empty file exists: pytest walks UP from a test file until
# it finds a conftest.py, and adds THAT directory to sys.path. This one makes
# `backend/` importable, so tests can do `from app.main import app` exactly
# like uvicorn does. Delete it and every test breaks with ModuleNotFoundError.
