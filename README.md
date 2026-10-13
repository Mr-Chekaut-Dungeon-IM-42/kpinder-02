# Kpinder

A dating service MVP, built as the semester-long project for a software engineering course. This repo is also where the course's own engineering standards (code style, git hooks, ADRs, Definition of Done) get established — Lab 1 is specifically about the scaffolding and standards, not a finished product.

## Idea

Kpinder has three core features: **auth** (login, registration, profile management), **matching** (candidate ranking by shared interests + location), and **chat** (real-time 1:1 messaging). The backend is organized as **vertical slices** — one bounded context per feature, each owning its own router/service/repository — rather than horizontal layers spanning the whole app. See [`spec.md`](spec.md) for the full architecture: component breakdown, data model (ER diagram), and how data updates for each key scenario.

## Stack

- **Backend**: Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL + PostGIS.
- **Frontend**: React, TypeScript, Vite.
- **Tooling**: `ruff` (backend lint/format), `eslint`+`prettier` (frontend lint/format), `pre-commit` (hook orchestration), `pytest` (tests), `uv` (backend dependency management), `npm` (frontend dependency management).

## Repo layout

```
backend/        FastAPI app — vertical slices (auth, matching, chat) + shared/ core
frontend/       React app — /login, /register (more slices land as phases ship)
spec.md         Architecture, data model, key scenarios — the target design
standards/      ADRs (MADR), Definition of Done, review checklist
ai/             Full AI-assisted design prompt trail + audit of scope cuts and AI corner-cutting
```

## Running locally

Requires Docker, `uv`, and `npm`.

1. **Database** (Postgres+PostGIS, from the repo root):

   ```sh
   docker compose up -d db
   ```

2. **Backend**:

   ```sh
   cd backend
   cp ../.env.example .env   # fill in DATABASE_URL/JWT_SECRET (defaults work against the compose db)
   uv sync
   uv run alembic upgrade head
   uv run uvicorn app.main:app --reload
   ```

   API is served at `http://localhost:8000` (interactive docs at `/docs`).

3. **Frontend** (in a separate terminal):

   ```sh
   cd frontend
   cp .env.example .env
   npm install
   npm run dev
   ```

   App is served at `http://localhost:5173`.

See [`backend/README.md`](backend/README.md) for backend-specific commands (lint, tests, migrations) and [`Makefile`](Makefile) for the `make lint`/`make test`/`make check` shortcuts run in CI.

## AI trail

This project's architecture was shaped through an AI-assisted design interview. The full prompt trail is in [`ai/prompts/`](ai/prompts/); [`ai/audit/lab-2.md`](ai/audit/lab-2.md) tracks both the AI's own corner-cutting (and how it was corrected) and the scope the team deliberately cut from the design described in `spec.md` to keep the MVP appropriately sized.
