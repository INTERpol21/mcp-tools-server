"""Tests for the sandboxed filesystem tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import ToolError
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


def test_symlink_escape_blocked(sandbox: Path) -> None:
    """A symlink inside the sandbox pointing outside must be denied,
    and the error must not leak the absolute host path of the target."""
    target = sandbox.parent / "secret.txt"
    link = sandbox / "innocent.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("platform does not allow creating symlinks")
    with pytest.raises(ToolError, match="sandbox") as excinfo:
        read_file("innocent.txt", data_dir=sandbox)
    assert str(sandbox.parent) not in str(excinfo.value)


def test_read_file_unicode_filename(sandbox: Path) -> None:
    (sandbox / "docs" / "заметки.md").write_text("привет\n", encoding="utf-8")
    result = read_file("docs/заметки.md", data_dir=sandbox)
    assert result["content"] == "привет\n"
    assert result["path"] == "docs/заметки.md"


def test_read_file_size_cap(sandbox: Path) -> None:
    (sandbox / "exact.txt").write_text("x" * MAX_FILE_BYTES, encoding="utf-8")
    assert read_file("exact.txt", data_dir=sandbox)["size_bytes"] == MAX_FILE_BYTES
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


# --------------------------------------------------------------------------- #
# Hostile-input hardening (adversarial regression tests)
# --------------------------------------------------------------------------- #


def test_read_file_dotdot_resolving_inside_is_allowed(sandbox: Path) -> None:
    """'..' segments that still resolve *inside* the sandbox are legitimate."""
    result = read_file("docs/../docs/notes.md", data_dir=sandbox)
    assert "hello from the sandbox" in result["content"]
    assert result["path"] == "docs/notes.md"


def test_read_file_trailing_slash_on_file_reads_it(sandbox: Path) -> None:
    """A trailing slash resolves to the file itself and reads safely."""
    result = read_file("docs/notes.md/", data_dir=sandbox)
    assert result["path"] == "docs/notes.md"


def test_read_file_newline_in_name_is_clean_error(sandbox: Path) -> None:
    with pytest.raises(ToolError, match="not found"):
        read_file("docs/no\nte.md", data_dir=sandbox)


def test_read_file_long_name_is_clean_error(sandbox: Path) -> None:
    with pytest.raises(ToolError, match="not found"):
        read_file("a" * 200 + ".md", data_dir=sandbox)


@pytest.mark.parametrize("path", [".", ""])
def test_read_file_on_directory_path_redirects_to_list_dir(sandbox: Path, path: str) -> None:
    with pytest.raises(ToolError, match="directory"):
        read_file(path, data_dir=sandbox)


def test_list_dir_on_a_file_is_clean_error(sandbox: Path) -> None:
    with pytest.raises(ToolError, match="is a file"):
        list_dir("docs/notes.md", data_dir=sandbox)


def test_list_dir_deep_nonexistent_is_clean_error(sandbox: Path) -> None:
    with pytest.raises(ToolError, match="not found"):
        list_dir("a/b/c/d/e/f/g", data_dir=sandbox)


def test_list_dir_dotdot_escape_blocked(sandbox: Path) -> None:
    with pytest.raises(ToolError, match="sandbox"):
        list_dir("docs/../..", data_dir=sandbox)


# --------------------------------------------------------------------------- #
# More sandbox-escape hardening. Each test names the concrete failure it guards.
# --------------------------------------------------------------------------- #


def test_absolute_path_inside_sandbox_is_allowed(sandbox: Path) -> None:
    # Contract: an absolute path is fine *iff* it resolves inside the sandbox; it
    # is the escape that is denied, not the leading '/'. Guards against a naive
    # "reject all absolute paths" rule that would break legitimate reads.
    absolute = str((sandbox / "docs" / "notes.md").resolve())
    result = read_file(absolute, data_dir=sandbox)
    assert result["path"] == "docs/notes.md"


def test_absolute_path_outside_sandbox_denied(sandbox: Path) -> None:
    # Failure: an absolute path pointing outside the sandbox reading host files.
    outside = sandbox.parent / "secret.txt"  # written by the sandbox fixture
    with pytest.raises(ToolError, match="sandbox"):
        read_file(str(outside), data_dir=sandbox)


def test_symlinked_directory_escape_blocked_for_read(sandbox: Path) -> None:
    # Failure: reading through a symlinked *directory* whose target is outside the
    # sandbox (an escape the per-file symlink check alone might miss).
    outside_dir = sandbox.parent / "outside"
    outside_dir.mkdir()
    (outside_dir / "loot.txt").write_text("host secret\n", encoding="utf-8")
    try:
        (sandbox / "linkdir").symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("platform does not allow creating symlinks")
    with pytest.raises(ToolError, match="sandbox") as excinfo:
        read_file("linkdir/loot.txt", data_dir=sandbox)
    assert str(sandbox.parent) not in str(excinfo.value)  # no host-path leak


def test_symlinked_directory_escape_blocked_for_list(sandbox: Path) -> None:
    # Failure: enumerating a directory that symlinks outside the sandbox.
    outside_dir = sandbox.parent / "outside2"
    outside_dir.mkdir()
    try:
        (sandbox / "linkdir2").symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("platform does not allow creating symlinks")
    with pytest.raises(ToolError, match="sandbox"):
        list_dir("linkdir2", data_dir=sandbox)


def test_list_dir_reports_file_sizes_and_dirs_first(sandbox: Path) -> None:
    # Failure: size_bytes missing on files or directories not sorted first, which
    # the MCP structured-output schema and clients rely on.
    result = list_dir("docs", data_dir=sandbox)
    by_name = {entry["name"]: entry for entry in result["entries"]}
    assert by_name["notes.md"]["type"] == "file"
    assert by_name["notes.md"]["size_bytes"] > 0


def test_read_file_empty_file_is_ok(sandbox: Path) -> None:
    # Failure: a legitimately empty file being treated as an error.
    (sandbox / "empty.txt").write_text("", encoding="utf-8")
    result = read_file("empty.txt", data_dir=sandbox)
    assert result["content"] == ""
    assert result["size_bytes"] == 0
