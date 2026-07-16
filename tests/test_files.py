"""Tests for the sandboxed filesystem tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.errors import ToolError
from app.tools.files import MAX_FILE_BYTES, list_dir, read_file


def test_read_file_happy_path(sandbox: Path) -> None:
    result = read_file("docs/notes.md", data_dir=sandbox)
    assert "hello from the sandbox" in result["content"]
    assert result["path"] == "docs/notes.md"
    assert result["size_bytes"] > 0


@pytest.mark.parametrize(
    "path",
    [
        "../secret.txt",
        "../../../../etc/passwd",
        "/etc/passwd",
        "docs/../../secret.txt",
    ],
)
def test_read_file_blocks_escapes(sandbox: Path, path: str) -> None:
    with pytest.raises(ToolError, match="sandbox"):
        read_file(path, data_dir=sandbox)


def test_read_file_size_cap(sandbox: Path) -> None:
    (sandbox / "big.txt").write_text("x" * (MAX_FILE_BYTES + 1), encoding="utf-8")
    with pytest.raises(ToolError, match="too large"):
        read_file("big.txt", data_dir=sandbox)


def test_read_file_rejects_binary(sandbox: Path) -> None:
    (sandbox / "image.bin").write_bytes(b"\x89PNG\x00\x00binary-not-text")
    with pytest.raises(ToolError, match="binary"):
        read_file("image.bin", data_dir=sandbox)


def test_read_file_missing_gives_clear_error(sandbox: Path) -> None:
    with pytest.raises(ToolError, match="not found"):
        read_file("docs/absent.md", data_dir=sandbox)


def test_list_dir_happy_path_sorted(sandbox: Path) -> None:
    result = list_dir(".", data_dir=sandbox)
    names = [entry["name"] for entry in result["entries"]]
    assert names == ["docs", "top.txt"]  # directories first, then files
    types = {entry["name"]: entry["type"] for entry in result["entries"]}
    assert types["docs"] == "dir"
    assert types["top.txt"] == "file"
    assert result["count"] == 2


def test_list_dir_blocks_escape(sandbox: Path) -> None:
    with pytest.raises(ToolError, match="sandbox"):
        list_dir("..", data_dir=sandbox)
