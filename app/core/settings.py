"""Runtime configuration resolved from environment variables.

See ``.env.example`` for the list of supported variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Bind all interfaces: intended for the containerized service (Docker/compose).
DEFAULT_HOST = "0.0.0.0"  # nosec B104
DEFAULT_PORT = 8082


def _default_data_dir() -> Path:
    """Repository-root ``data/`` directory (independent of the CWD).

    This is the seeded directory that actually holds ``demo.db``, ``docs/`` and
    ``search_index.json`` (matching README and ``.env.example``). settings.py lives
    at ``app/core/``, so the repo root is two parents up. The earlier ``app/data``
    default held only a stale ``demo.db``, so a bare ``python -m app.server`` run
    broke ``search_web`` and registered zero ``docs://`` resources.
    """
    return Path(__file__).resolve().parents[2] / "data"


@dataclass(frozen=True)
class Settings:
    """Immutable server settings, resolved once at startup."""

    data_dir: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    @property
    def index_path(self) -> Path:
        """Location of the offline search index used by ``search_web``."""
        return self.data_dir / "search_index.json"

    @property
    def db_path(self) -> Path:
        """Location of the demo SQLite database used by ``query_database``."""
        return self.data_dir / "demo.db"

    @property
    def docs_dir(self) -> Path:
        """Directory whose files are published as ``docs://`` MCP resources."""
        return self.data_dir / "docs"


def load_settings() -> Settings:
    """Build :class:`Settings` from the process environment."""
    data_dir = Path(os.environ.get("DATA_DIR") or _default_data_dir()).resolve()
    host = os.environ.get("MCP_HOST", DEFAULT_HOST)
    raw_port = os.environ.get("MCP_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise RuntimeError(f"MCP_PORT must be an integer, got {raw_port!r}.") from exc
    return Settings(data_dir=data_dir, host=host, port=port)
