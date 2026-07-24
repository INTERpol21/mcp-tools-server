FROM python:3.14-slim

WORKDIR /app

# requirements.txt is generated from pyproject.toml + uv.lock (see `make lock`).
COPY requirements.txt ./
# BuildKit cache mount: a dependency bump re-downloads only the changed
# wheels instead of the whole set (--no-cache-dir kept nothing between builds).
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

COPY app ./app
COPY data ./data

ENV DATA_DIR=/app/data \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8082 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Run as a non-root user (data dir must be writable for the lazily-seeded demo.db).
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8082

# Streamable-HTTP transport: check the port is accepting connections. Reads
# MCP_PORT so overriding the documented env var does not leave the container
# permanently unhealthy against a hardcoded 8082.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os, socket, sys; s=socket.socket(); s.settimeout(2); sys.exit(0 if s.connect_ex(('127.0.0.1', int(os.environ.get('MCP_PORT', '8082'))))==0 else 1)"

CMD ["python", "-m", "app.server", "--transport", "http"]
