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

# Input/output size bounds. The row-count cap alone does not bound *size*: a
# single row can conjure arbitrary bytes via zeroblob()/randomblob(), so cap
# the raw SQL length up front and the materialised result as it streams in.
MAX_SQL_CHARS = 20_000
MAX_CELL_BYTES = 1_000_000  # 1 MB per cell (blobs are still summarised, not returned)
MAX_RESULT_BYTES = 8_000_000  # 8 MB of materialised cell data per query

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
    _arg1: "str | None",
    _arg2: "str | None",
    _db_name: "str | None",
    _trigger: "str | None",
) -> int:
    """SQLite authorizer hook: allow read operations, deny everything else."""
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
    if isinstance(value, (bytes, bytearray)):
        return f"<blob: {len(value)} bytes>"
    return value


def _value_bytes(value: object) -> int:
    """Approximate materialised size of a cell, for the result-size budget."""
    if isinstance(value, (bytes, bytearray, str)):
        return len(value)
    return 8  # numbers / NULL: small fixed cost


def query_database(
    sql: str, max_rows: int = DEFAULT_MAX_ROWS, *, db_path: Path
) -> dict[str, Any]:
    """Execute a single read-only SELECT statement and return capped rows.

    Raises ToolError for empty input, multi-statement payloads, non-SELECT
    statements and any SQL error -- one clear line, never a traceback.
    """
    if not sql or not sql.strip():
        raise ToolError("SQL query must not be empty.")
    if len(sql) > MAX_SQL_CHARS:
        raise ToolError(
            f"SQL query too long: {len(sql)} chars exceeds the {MAX_SQL_CHARS}-char limit."
        )
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
            # Stream row-by-row so an oversized cell is caught after a single
            # fetch, before it can be amplified across many rows.
            rows: list[list[Any]] = []
            truncated = False
            total_bytes = 0
            while True:
                raw_row = cursor.fetchone()
                if raw_row is None:
                    break
                if len(rows) >= limit:
                    truncated = True
                    break
                json_row: list[Any] = []
                for value in raw_row:
                    if isinstance(value, (bytes, bytearray, str)) and len(value) > MAX_CELL_BYTES:
                        raise ToolError(
                            f"Result cell too large: {len(value)} bytes exceeds the "
                            f"{MAX_CELL_BYTES}-byte limit; narrow the query."
                        )
                    total_bytes += _value_bytes(value)
                    json_row.append(_to_json_value(value))
                if total_bytes > MAX_RESULT_BYTES:
                    raise ToolError(
                        f"Result too large: over {MAX_RESULT_BYTES} bytes materialised; "
                        "add a tighter filter or lower max_rows."
                    )
                rows.append(json_row)
        except (sqlite3.Error, sqlite3.Warning) as exc:
            # SQLite phrases authorizer denials two ways: "not authorized"
            # (statements) and "authorization denied" (pragma functions).
            message = str(exc).lower()
            if "not authorized" in message or "authorization denied" in message:
                raise ToolError(_READ_ONLY_MESSAGE) from exc
            raise ToolError(f"SQL error: {exc}") from exc
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    finally:
        connection.close()
