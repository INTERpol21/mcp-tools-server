"""Publish the files under ``data/docs`` as ``docs://`` MCP resources.

Every read goes through ``files.read_file`` with the docs directory as the
sandbox root, so resources are exactly as hardened as the read_file tool: any
path that resolves outside the root (via "..", a location outside it, or a
symlink target), oversized files and binary content are all rejected with the
same clean errors. Absolute paths are allowed only when they resolve inside
the root.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.resources import FunctionResource
from pydantic import AnyUrl

from app.core.settings import Settings
from app.tools import files

# Resource mime types by docs file extension (fallback: plain text).
_DOC_MIME_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
}


def _doc_mime_type(name: str) -> str:
    """Mime type for a docs file, by extension."""
    return _DOC_MIME_TYPES.get(Path(name).suffix.lower(), "text/plain")


def _make_doc_reader(name: str, docs_dir: Path) -> Callable[[], str]:
    """Lazy reader for one docs file (binds ``name`` per loop iteration)."""

    def _read() -> str:
        return files.read_file(name, data_dir=docs_dir)["content"]

    return _read


def register_doc_resources(server: FastMCP, settings: Settings) -> int:
    """Publish ``data/docs`` as a ``docs://{name}`` template plus concrete resources.

    Returns the number of concrete file resources registered (0 when the docs
    directory is absent; the template still answers direct reads).
    """
    docs_dir = settings.docs_dir

    @server.resource("docs://{name}", name="doc", mime_type="text/plain")
    def get_doc(name: str) -> str:
        """Text of one file from the server's data/docs directory, by file name."""
        return files.read_file(name, data_dir=docs_dir)["content"]

    if not docs_dir.is_dir():
        return 0  # nothing to list; the template still answers direct reads
    count = 0
    for child in sorted(docs_dir.iterdir(), key=lambda entry: entry.name.lower()):
        if not child.is_file() or child.name.startswith("."):
            continue
        server.add_resource(
            FunctionResource(
                uri=AnyUrl(f"docs://{child.name}"),
                name=child.name,
                description=f"Demo document served from data/docs/{child.name}.",
                mime_type=_doc_mime_type(child.name),
                fn=_make_doc_reader(child.name, docs_dir),
            )
        )
        count += 1
    return count
