.PHONY: lint test test-unit test-int test-integration test-mut mutation test-e2e test-all build check

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

test-unit:
	cd backend && uv run pytest -q

test-integration:
	cd backend && uv run pytest -q -m integration

mutation:
	cd backend && \
	DATABASE_URL=$${DATABASE_URL:-postgresql+asyncpg://kpinder:kpinder@localhost:5433/kpinder} \
	JWT_SECRET=$${JWT_SECRET:-mutmut-dummy-secret} \
	uv run --with mutmut mutmut run

test-e2e:
	cd backend && uv run pytest -q -m e2e

test-all: test-unit test-integration test-e2e

build:
	cd backend && uv build

check: lint test build
