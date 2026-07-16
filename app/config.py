"""Runtime configuration resolved from environment variables.

See ``.env.example`` for the list of supported variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8082


def _default_data_dir() -> Path:
    """Repository-local ``data/`` directory (independent of the CWD)."""
    return Path(__file__).resolve().parent.parent / "data"


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
