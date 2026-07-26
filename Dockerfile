# SokoLink BACKEND image — built by Railway from the repo ROOT.
#
# WHY a Dockerfile: this is a monorepo (backend/, frontend/, docs/, shared/).
# Railway's auto-detector (Railpack) scans the root, finds no requirements.txt
# there, and can't pick an app — that's what failed the earlier builds. A
# Dockerfile removes the guesswork: we say exactly what to build. When Railway
# sees this file it uses the Dockerfile builder automatically; no dashboard
# Root Directory setting is needed. (The frontend deploys as its own service.)

FROM python:3.11-slim

# Cleaner, faster Python in a container; no pip cache bloat in the image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first so this layer is cached until requirements.txt changes.
# psycopg[binary] + argon2-cffi ship manylinux wheels, so no compiler needed.
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# Then the backend source. .dockerignore keeps .venv / media / caches out.
COPY backend/ ./

# Railway injects $PORT at runtime. Apply DB migrations (idempotent — a no-op
# when already at head), then serve. Shell form so $PORT expands.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
