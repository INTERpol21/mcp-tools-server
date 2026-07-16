.PHONY: install install-dev run run-stdio run-http seed test lint

install:
	pip install -r requirements.txt

install-dev: install
	pip install pytest pytest-asyncio ruff

run: run-http  ## platform default: streamable HTTP on :8082 (endpoint /mcp)

run-stdio:
	python -m app.server --transport stdio

run-http:
	python -m app.server --transport http

seed:
	python -m app.tools.seed

test:
	pytest

lint:
	ruff check app tests
