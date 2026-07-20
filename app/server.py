"""FastMCP wiring for the ``portfolio-tools`` MCP server.

Tool logic lives in ``app.tools`` as pure typed functions; this module only
registers thin wrappers on a FastMCP instance and selects a transport. The
wrapper docstrings double as tool descriptions -- they are the "UI" an LLM
uses to pick tools, so they carry schemas, examples and constraints. The
TypedDict return annotations double as MCP output schemas, so every result
is also emitted as ``structuredContent`` next to the readable JSON text.
The files under ``data/docs`` are additionally published as ``docs://``
resources.

Run:
    python -m app.server                     # stdio (default)
    python -m app.server --transport http    # streamable HTTP on MCP_PORT
"""

from __future__ import annotations

import argparse
import sys

from mcp.server.fastmcp import FastMCP

from app.core.logging import configure_logging, get_logger, log_event
from app.core.settings import Settings, load_settings
from app.resources.docs import register_doc_resources
from app.tools import database, files, search

SERVER_NAME = "portfolio-tools"

log = get_logger("mcp.tools")

_INSTRUCTIONS = (
    "Demo toolbox for an AI-platform portfolio. Provides offline web search "
    "over a curated index, read-only SQL over a demo job-market SQLite "
    "database, and sandboxed file access under the server's data directory. "
    "Project docs are also exposed as docs:// resources. All tools are "
    "deterministic and safe: destructive operations are rejected by design."
)


def create_server(settings: Settings | None = None) -> FastMCP:
    """Build a FastMCP server with all four tools and docs:// resources registered.

    Accepting ``settings`` keeps the factory injectable: tests point it at a
    temporary data directory without touching process environment.
    """
    configure_logging()
    settings = settings or load_settings()
    server = FastMCP(
        SERVER_NAME,
        instructions=_INSTRUCTIONS,
        host=settings.host,
        port=settings.port,
    )

    @server.tool()
    def search_web(query: str, max_results: int = 5) -> search.SearchWebResult:
        """Search a curated index of LLM/RAG/MCP engineering articles.

        Offline demo stub: results come from a local, deterministic index of
        14 hand-picked entries ranked by keyword overlap with the query. In
        production this would call a real search API; the contract would not
        change.

        Args:
            query: Free-text query, e.g. "rag chunking strategies".
            max_results: Maximum number of results, 1-20 (default 5).

        Returns:
            {"query", "results": [{"title", "url", "snippet", "score"}, ...],
            "total_matches", "source": "offline_index"} -- best match first.
        """
        log_event(log, "search_web called", query_len=len(query), max_results=max_results)
        return search.search_web(query, max_results, index_path=settings.index_path)

    @server.tool()
    def query_database(sql: str, max_rows: int = 50) -> database.QueryDatabaseResult:
        """Run one read-only SELECT against the demo IT job-market database.

        SQLite schema:
            companies(id, name, industry, city)
            vacancies(id, company_id, title, grade, salary_rub, stack)
            applications(id, vacancy_id, applied_at, status)

        Exactly one SELECT statement is accepted. Writes, DDL, PRAGMA,
        ATTACH and multi-statement payloads are rejected. Example:
        "SELECT c.name, v.title FROM vacancies v JOIN companies c
        ON c.id = v.company_id WHERE v.grade = 'senior'".

        Args:
            sql: A single SELECT statement.
            max_rows: Row cap for the result, 1-200 (default 50).

        Returns:
            {"columns", "rows", "row_count", "truncated"}.
        """
        # Log the shape, never the SQL text or rows (could carry sensitive data).
        log_event(log, "query_database called", sql_chars=len(sql), max_rows=max_rows)
        return database.query_database(sql, max_rows, db_path=settings.db_path)

    @server.tool()
    def read_file(path: str) -> files.ReadFileResult:
        """Read a UTF-8 text file from the server's sandboxed data directory.

        Relative and absolute paths are both accepted, but only if they resolve
        inside the data directory; any path that escapes it (via "..", a location
        outside the root, or a symlink target) is denied. Files are capped at
        100 KB and must be text. Use list_dir first to discover available files,
        e.g. read_file("docs/pipeline.md").

        Args:
            path: File path, relative to the data directory or absolute-inside-it.

        Returns:
            {"path", "size_bytes", "content"}.
        """
        log_event(log, "read_file called", path=path)
        return files.read_file(path, data_dir=settings.data_dir)

    @server.tool()
    def list_dir(path: str = ".") -> files.ListDirResult:
        """List files and folders inside the server's sandboxed data directory.

        Same sandbox rules as read_file: paths are relative to the data
        directory and cannot escape it. Entries are sorted directories-first.

        Args:
            path: Directory path relative to the data directory (default ".").

        Returns:
            {"path", "entries": [{"name", "type", "size_bytes"?}, ...], "count"}.
        """
        log_event(log, "list_dir called", path=path)
        return files.list_dir(path, data_dir=settings.data_dir)

    resource_count = register_doc_resources(server, settings)
    log_event(
        log,
        "MCP server built",
        data_dir=str(settings.data_dir),
        tools=4,
        doc_resources=resource_count,
    )
    return server


def _run_http(server: FastMCP) -> None:
    """Run over streamable HTTP, falling back to SSE for older SDKs."""
    try:
        server.run(transport="streamable-http")
    except ValueError:
        print(
            "This mcp SDK build does not support 'streamable-http'; "
            "falling back to the legacy SSE transport.",
            file=sys.stderr,
        )
        server.run(transport="sse")


# Module-level instance so `mcp dev app/server.py` (MCP Inspector) finds it;
# constructing it only lists data/docs to register resources (no file reads).
server = create_server()


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m app.server",
        description="Run the portfolio-tools MCP server.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="stdio for local clients (default); http serves streamable HTTP "
        "on MCP_HOST:MCP_PORT (default 0.0.0.0:8082)",
    )
    args = parser.parse_args(argv)
    if args.transport == "http":
        _run_http(server)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
