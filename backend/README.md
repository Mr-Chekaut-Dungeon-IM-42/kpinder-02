# Kpinder Backend

FastAPI backend for Kpinder dating service MVP. See the [repo root README](../README.md) for the full local setup (Docker DB + frontend); this file covers backend-only commands.

## Setup

```sh
cp ../.env.example .env   # DATABASE_URL, JWT_SECRET, JWT_EXPIRE_MINUTES, CORS_ORIGINS
uv sync
```

Requires a running Postgres+PostGIS instance (`docker compose up -d db` from the repo root) matching `DATABASE_URL`.

## Migrations

```sh
uv run alembic upgrade head          # apply
uv run alembic revision --autogenerate -m "message"   # generate (review by hand before committing — ADR-0008)
```

## Run

```sh
uv run uvicorn app.main:app --reload
```

Serves on `http://localhost:8000` (`/docs` for interactive OpenAPI docs, `/health` for the smoke-test endpoint).

## Lint, test, build

```sh
uv run ruff check . && uv run ruff format --check .   # lint
uv run pytest -q                                       # unit tests (integration tests excluded by default)
uv run pytest -q -m integration                        # integration tests (requires Docker — testcontainers)
uv build                                               # build
```

Or via the root `Makefile`: `make lint`, `make test`, `make test-integration`, `make build`, `make check` (lint+test+build).
