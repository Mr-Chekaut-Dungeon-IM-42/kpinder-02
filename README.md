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

### Running the API on a specific loopback address

By default the API binds to `127.0.0.1:8000`. To run it on a different address/port instead — e.g. to run multiple instances side by side, each on its own IP but the same port — set `APP_HOST`/`APP_PORT` in the repo-root `.env` (copy from [`.env.example`](.env.example)):

```
APP_HOST=127.0.0.6
APP_PORT=8000
```

Then:

```sh
make run-api                    # bare-metal: uv run uvicorn, reads APP_HOST/APP_PORT from root .env
# or
docker compose up -d backend    # containerized: port-published to ${APP_HOST}:${APP_PORT} on the host
```

**macOS only**: the loopback interface only has `127.0.0.1` assigned by default — unlike Linux, where the whole `127.0.0.0/8` block is usable out of the box. Binding to any other `127.x.x.x` address (`127.0.0.6` above, or the `127.0.0.3` the `db-test` compose service already uses) first requires adding it as an alias, once per reboot:

```sh
sudo ifconfig lo0 alias 127.0.0.6 up
```

This is a one-time-per-session OS-level step — it makes the address bindable at all, independently of `APP_HOST`/`.env`, and isn't specific to this project (any other process wanting that same address needs the same alias). It doesn't persist across a reboot; re-run it if the address stops binding after restarting your Mac.

## AI trail

This project's architecture was shaped through an AI-assisted design interview. The full prompt trail is in [`ai/prompts/`](ai/prompts/); [`ai/audit/lab-2.md`](ai/audit/lab-2.md) tracks both the AI's own corner-cutting (and how it was corrected) and the scope the team deliberately cut from the design described in `spec.md` to keep the MVP appropriately sized.
