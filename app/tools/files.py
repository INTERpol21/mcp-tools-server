"""Sandboxed filesystem tools: read files and list directories under DATA_DIR.

Sandbox rule: every user-supplied path is fully resolved (symlinks and
``..`` included) and the result must stay inside the configured data
directory, checked with ``Path.is_relative_to`` on resolved paths.
Error messages echo the caller's path, never absolute host paths.
"""

from __future__ import annotations

from pathlib import Path

from typing_extensions import NotRequired, TypedDict

from app.core.errors import ToolError

MAX_FILE_BYTES = 100 * 1024


class ReadFileResult(TypedDict):
    """Shape of a successful ``read_file`` call (drives MCP structured output)."""

    path: str
    size_bytes: int
    content: str


class DirEntry(TypedDict):
    """One ``list_dir`` entry; ``size_bytes`` is present for files only."""

    name: str
    type: str
    size_bytes: NotRequired[int]


class ListDirResult(TypedDict):
    """Shape of a successful ``list_dir`` call (drives MCP structured output)."""

    path: str
    entries: list[DirEntry]
    count: int


def _resolve_inside_sandbox(path: str, data_dir: Path) -> tuple[Path, Path]:
    """Resolve ``path`` against the sandbox root; deny anything that escapes."""
    base = data_dir.resolve()
    raw = Path(path)
    candidate = raw if raw.is_absolute() else base / raw
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        # Unresolvable input: symlink loops, NUL bytes, over-long paths.
        raise ToolError(f"Invalid path: {path!r}.") from exc
    if not resolved.is_relative_to(base):
        raise ToolError(f"Access denied: '{path}' escapes the data directory sandbox.")
    return resolved, base


def _display_path(resolved: Path, base: Path) -> str:
    """Sandbox-relative POSIX path for display in results."""
    return "." if resolved == base else resolved.relative_to(base).as_posix()


def read_file(path: str, *, data_dir: Path) -> ReadFileResult:
    """Read a UTF-8 text file inside the sandbox, capped at MAX_FILE_BYTES."""
    resolved, base = _resolve_inside_sandbox(path, data_dir)
    if not resolved.exists():
        raise ToolError(
            f"File not found: '{path}' (paths are relative to the data directory)."
        )
    if resolved.is_dir():
        raise ToolError(f"'{path}' is a directory; use list_dir to browse it.")
    try:
        size = resolved.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ToolError(
                f"File too large: {size} bytes (limit is {MAX_FILE_BYTES} bytes)."
            )
        raw_bytes = resolved.read_bytes()
    except OSError as exc:
        raise ToolError(
            f"Could not read '{path}': {exc.strerror or type(exc).__name__}."
        ) from exc
    if b"\x00" in raw_bytes:
        raise ToolError(
            f"'{path}' looks like a binary file; only UTF-8 text is supported."
        )
    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(f"'{path}' is not valid UTF-8 text.") from exc
    return {
        "path": _display_path(resolved, base),
        "size_bytes": size,
        "content": content,
    }


def list_dir(path: str = ".", *, data_dir: Path) -> ListDirResult:
    """List a directory inside the sandbox, directories first."""
    resolved, base = _resolve_inside_sandbox(path, data_dir)
    if not resolved.exists():
        raise ToolError(f"Directory not found: '{path}'.")
    if not resolved.is_dir():
        raise ToolError(f"'{path}' is a file; use read_file to read it.")
    try:
        children = sorted(
            resolved.iterdir(),
            key=lambda child: (not child.is_dir(), child.name.lower()),
        )
        entries: list[DirEntry] = []
        for child in children:
            entry: DirEntry = {
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
            }
            if child.is_file():
                entry["size_bytes"] = child.stat().st_size
            entries.append(entry)
    except OSError as exc:
        raise ToolError(
            f"Could not list '{path}': {exc.strerror or type(exc).__name__}."
        ) from exc
    return {
        "path": _display_path(resolved, base),
        "entries": entries,
        "count": len(entries),
    }
