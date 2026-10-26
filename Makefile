.PHONY: lint test test-unit test-int test-integration test-mut mutation mutation-results test-e2e test-all build check run-api seed-load load profile

run-api:
	set -a; [ -f .env ] && . ./.env; set +a; \
	cd backend && uv run uvicorn app.main:app --host "$${APP_HOST:-127.0.0.2}" --port "$${APP_PORT:-8000}" --reload

ENV_PATH := backend/.env

run-api:
	set -a; [ -f $(ENV_PATH) ] && . $(ENV_PATH); set +a; \
	cd backend && uv run uvicorn app.main:app --host "$${APP_HOST:-127.0.0.1}" --port "$${APP_PORT:-8000}" --reload

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

test-unit:
	cd backend && uv run pytest -q

test-integration:
	cd backend && uv run pytest -q -m integration

mutation:
	set -a; [ -f .env ] && . ./.env; set +a; \
	cd backend && \
	DATABASE_URL=$${DATABASE_URL:-postgresql+asyncpg://kpinder:kpinder@$${DB_HOST:-localhost}:$${DB_PORT:-5432}/kpinder} \
	JWT_SECRET=$${JWT_SECRET:-mutmut-dummy-secret} \
	uv run --with mutmut mutmut run

mutation-results:
	cd backend && uv run --with mutmut mutmut results

test-e2e:
	cd backend && uv run pytest -q -m e2e

test-all: test-unit test-integration test-e2e

build:
	cd backend && uv build

check: lint test build

# Lab 5 — performance tooling. All three assume a backend already running
# against a DB seeded via `seed-load` (see ai/audit/lab-5.md for the full
# methodology and standards/adr/0026 for what this found).

seed-load:
	set -a; [ -f $(ENV_PATH) ] && . $(ENV_PATH); set +a; \
	cd backend && uv run python scripts/seed_load_data.py \
		--database-url "$${LOAD_DATABASE_URL:-postgresql://kpinder:kpinder@127.0.0.2:5432/kpinder}" \
		--users "$${LOAD_USERS:-50000}"

load:
	cd backend && uv run locust -f loadtest/locustfile.py \
		--host "$${LOAD_HOST:-http://127.0.0.2:8000}" \
		--headless --users "$${LOAD_CONCURRENCY:-150}" --spawn-rate 25 \
		--run-time "$${LOAD_DURATION:-60s}" --csv /tmp/kpinder_load

profile:
	@echo "Attaching py-spy to a running uvicorn process (macOS needs sudo for this)."
	@echo "Find the pid first: pgrep -f 'uvicorn app.main:app'"
	@test -n "$$PID" || (echo "Usage: make profile PID=<uvicorn pid> [DURATION=60]"; exit 1)
	sudo .venv/bin/py-spy record -o /tmp/kpinder_flame.svg \
		--pid "$$PID" --duration "$${DURATION:-60}" --rate 100
