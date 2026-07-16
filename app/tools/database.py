"""Read-only SQL access to the bundled demo SQLite database.

Defence in depth, in order:

1. the connection is opened in read-only mode (SQLite URI ``mode=ro``);
2. an authorizer callback allows SELECT/READ only and denies everything
   else (writes, DDL, PRAGMA, ATTACH, transactions);
3. multi-statement payloads (``SELECT 1; DROP ...``) are rejected up front,
   with ``sqlite3.complete_statement`` so ``;`` inside string literals is fine;
4. result sets are capped to protect the model's context window.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.tools.errors import ToolError
from app.tools.seed import ensure_database

DEFAULT_MAX_ROWS = 50
HARD_ROW_CAP = 200

# SQLITE_RECURSIVE is needed for WITH RECURSIVE; the constant is missing from
# some older sqlite3 builds, so fall back to its numeric value (33).
_ALLOWED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        getattr(sqlite3, "SQLITE_RECURSIVE", 33),
    }
)

_READ_ONLY_MESSAGE = (
    "Query rejected: only read-only SELECT queries are allowed "
    "(writes, DDL, PRAGMA, ATTACH and transactions are blocked)."
)


def _authorizer(
    action: int,
    arg1: "str | None",
    arg2: "str | None",
    db_name: "str | None",
    trigger: "str | None",
) -> int:
    """SQLite authorizer hook: allow read operations, deny everything else."""
    del arg1, arg2, db_name, trigger  # part of the sqlite3 callback contract
    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _has_multiple_statements(sql: str) -> bool:
    """Detect ``stmt1; stmt2`` payloads while allowing ';' inside literals."""
    for position, char in enumerate(sql):
        if char != ";":
            continue
        prefix_complete = sqlite3.complete_statement(sql[: position + 1])
        if prefix_complete and sql[position + 1 :].strip():
            return True
    return False


def _connect_read_only(db_path: Path) -> sqlite3.Connection:
    """Open the database with SQLite-enforced read-only mode."""
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _to_json_value(value: object) -> object:
    """Make a SQLite cell value JSON-serialisable."""
    if isinstance(value, bytes):
        return f"<blob: {len(value)} bytes>"
    return value


def query_database(
    sql: str, max_rows: int = DEFAULT_MAX_ROWS, *, db_path: Path
) -> dict[str, Any]:
    """Execute a single read-only SELECT statement and return its rows.

    Args:
        sql: Exactly one SELECT statement.
        max_rows: Row cap for the result set (clamped to 1..200).
        db_path: Demo database location; seeded automatically if missing.

    Returns:
        Dict with ``columns``, ``rows``, ``row_count`` and ``truncated``.

    Raises:
        ToolError: For empty input, multi-statement payloads, non-SELECT
            statements and any SQL error (clear message, no traceback).
    """
    if not sql or not sql.strip():
        raise ToolError("SQL query must not be empty.")
    if _has_multiple_statements(sql):
        raise ToolError(
            "Multiple SQL statements are not allowed; send exactly one SELECT statement."
        )
    limit = max(1, min(int(max_rows), HARD_ROW_CAP))

    ensure_database(db_path)
    connection = _connect_read_only(db_path)
    try:
        connection.set_authorizer(_authorizer)
        try:
            cursor = connection.execute(sql)
            if cursor.description is None:
                raise ToolError(
                    "Statement produced no result set; only SELECT queries are supported."
                )
            columns = [description[0] for description in cursor.description]
            fetched = cursor.fetchmany(limit + 1)
        except (sqlite3.Error, sqlite3.Warning) as exc:
            if "not authorized" in str(exc).lower():
                raise ToolError(_READ_ONLY_MESSAGE) from exc
            raise ToolError(f"SQL error: {exc}") from exc
        truncated = len(fetched) > limit
        rows = [[_to_json_value(value) for value in row] for row in fetched[:limit]]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    finally:
        connection.close()
