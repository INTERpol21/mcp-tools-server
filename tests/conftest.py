"""Shared fixtures: repository paths and a temporary sandboxed data directory."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def index_path() -> Path:
    """The committed offline search index (deterministic test data)."""
    return REPO_ROOT / "data" / "search_index.json"


@pytest.fixture()
def sandbox(tmp_path: Path) -> Path:
    """A data directory with sample files, plus a secret outside of it."""
    data_dir = tmp_path / "data"
    docs = data_dir / "docs"
    docs.mkdir(parents=True)
    (docs / "notes.md").write_text("# Notes\nhello from the sandbox\n", encoding="utf-8")
    (docs / "pipeline.md").write_text(
        "# Pipeline\nretrieve -> rerank -> generate\n", encoding="utf-8"
    )
    (data_dir / "top.txt").write_text("top-level file\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("do not read me\n", encoding="utf-8")
    return data_dir


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Location for a throwaway demo database (seeded on demand)."""
    return tmp_path / "demo.db"
