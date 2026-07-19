FROM python:3.10-slim

WORKDIR /app

# requirements.txt is generated from pyproject.toml + uv.lock (see `make lock`).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

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

# Streamable-HTTP transport: check the port is accepting connections.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import socket, sys; s=socket.socket(); s.settimeout(2); sys.exit(0 if s.connect_ex(('127.0.0.1', 8082))==0 else 1)"

CMD ["python", "-m", "app.server", "--transport", "http"]
