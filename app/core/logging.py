"""Structured (JSON) logging for the MCP server — one JSON object per line.

The other platform services log this way; the MCP server previously logged
nothing, so tool calls, rejections and startup were invisible in operation.
Keep messages human-readable (what happened, with what, the outcome) while
staying machine-parseable. Never log file contents, full SQL results, or the
demo DB rows — only shapes/sizes/paths — so the logs can't leak data.
"""

from __future__ import annotations

import json
import logging
from typing import Any

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """One JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Structured extras attached via logger.info(..., extra={...}).
        for key, value in getattr(record, "context", {}).items():
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger (idempotent).

    Writes to stderr so it never corrupts the stdio MCP transport, which uses
    stdout for the JSON-RPC protocol frames.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    import sys

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, msg: str, **context: Any) -> None:
    """Emit an info record with structured, non-sensitive context fields."""
    logger.info(msg, extra={"context": context})
