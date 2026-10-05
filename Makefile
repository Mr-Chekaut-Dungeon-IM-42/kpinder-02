.PHONY: lint test build check

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

test:
	cd backend && uv run pytest -q

build:
	cd backend && uv build

check: lint test build
