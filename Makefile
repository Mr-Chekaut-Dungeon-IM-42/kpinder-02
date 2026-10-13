.PHONY: lint test test-unit test-int test-integration test-mut mutation test-e2e test-all build check

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

test: test-unit

test-unit:
	cd backend && uv run pytest -q

test-int: test-integration

test-integration:
	cd backend && uv run pytest -q -m integration

test-mut: mutation

mutation:
	cd backend && uv run --with mutmut mutmut run

test-e2e:
	cd backend && uv run pytest -q -m e2e

test-all: test-unit test-integration test-e2e

build:
	cd backend && uv build

check: lint test build
