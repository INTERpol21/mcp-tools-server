.PHONY: install install-dev run run-stdio run-http seed test lint typecheck lock

# uv is the source of truth; requirements*.txt are exported from uv.lock for Docker/pip users.
install:
	uv sync --frozen --no-dev

install-dev:
	uv sync --frozen

run: run-http  ## platform default: streamable HTTP on :8082 (endpoint /mcp)

run-stdio:
	uv run python -m app.server --transport stdio

run-http:
	uv run python -m app.server --transport http

seed:
	uv run python -m app.tools.seed

test:
	uv run pytest

lint:
	uv run ruff check app tests

typecheck:
	uv run mypy app

# Regenerate uv.lock and the exported requirements files after editing pyproject.toml.
lock:
	uv lock
	uv export --frozen --no-hashes --no-dev --no-emit-project -o requirements.txt
	uv export --frozen --no-hashes --only-dev --no-emit-project -o requirements-dev.txt
