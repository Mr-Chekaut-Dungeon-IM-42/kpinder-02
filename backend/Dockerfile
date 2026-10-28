FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Built from the REPO ROOT (not backend/) as of Lab 5 — matching-core
# (ADR-0026) is a local uv path dependency one level up from
# backend/pyproject.toml (../libs/matching-core), so it has to be inside
# the build context. See docker-compose.yml's backend service and
# railway.json at the repo root; DEFENSE.md documents the one-time Railway
# dashboard change this requires (service Root Directory -> repo root).
COPY libs/matching-core ./libs/matching-core
COPY backend/pyproject.toml backend/uv.lock* ./backend/
WORKDIR /app/backend
RUN uv sync --no-dev --no-install-project

COPY backend/. .
RUN uv sync --no-dev

EXPOSE 8000

CMD uv run --no-dev alembic upgrade head && uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port 8000
