FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data

ENV DATA_DIR=/app/data \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8082

EXPOSE 8082

CMD ["python", "-m", "app.server", "--transport", "http"]
