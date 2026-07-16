"""Tests for the read-only SQL tool and the demo database seeder."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.tools.database import _connect_read_only, query_database
from app.tools.errors import ToolError
from app.tools.seed import ensure_database


def _count_companies(db_path: Path) -> int:
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    finally:
        connection.close()


def test_seed_is_idempotent(db_path: Path) -> None:
    assert ensure_database(db_path) is True
    assert ensure_database(db_path) is False
    assert _count_companies(db_path) == 6


def test_select_returns_rows(db_path: Path) -> None:
    result = query_database(
        "SELECT name, city FROM companies ORDER BY id", db_path=db_path
    )
    assert result["columns"] == ["name", "city"]
    assert result["row_count"] == 6
    assert result["truncated"] is False


def test_join_query_works(db_path: Path) -> None:
    sql = (
        "SELECT c.name, v.title, v.salary_rub FROM vacancies v "
        "JOIN companies c ON c.id = v.company_id "
        "WHERE v.grade = 'senior' ORDER BY v.salary_rub DESC"
    )
    result = query_database(sql, db_path=db_path)
    assert result["columns"] == ["name", "title", "salary_rub"]
    assert result["row_count"] >= 3
    salaries = [row[2] for row in result["rows"]]
    assert salaries == sorted(salaries, reverse=True)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO companies VALUES (99, 'Evil Corp', 'X', 'Nowhere')",
        "UPDATE vacancies SET salary_rub = 1",
        "DELETE FROM applications",
        "DROP TABLE companies",
        "CREATE TABLE pwned (id INTEGER)",
        "PRAGMA user_version = 99",
        "ATTACH DATABASE ':memory:' AS other",
        "WITH x AS (SELECT 1) INSERT INTO companies SELECT 99, 'a', 'b', 'c' FROM x",
    ],
)
def test_non_select_statements_rejected(db_path: Path, sql: str) -> None:
    ensure_database(db_path)
    with pytest.raises(ToolError, match="read-only"):
        query_database(sql, db_path=db_path)


def test_multi_statement_injection_rejected(db_path: Path) -> None:
    ensure_database(db_path)
    with pytest.raises(ToolError, match="[Mm]ultiple"):
        query_database(
            "SELECT * FROM companies; DROP TABLE companies", db_path=db_path
        )
    # Even two harmless SELECTs are refused: the guard is statement-count-based.
    with pytest.raises(ToolError, match="[Mm]ultiple"):
        query_database("SELECT 1; SELECT 2", db_path=db_path)
    # The table must have survived the attempt.
    assert _count_companies(db_path) == 6


def test_semicolon_inside_literal_is_allowed(db_path: Path) -> None:
    result = query_database("SELECT 'a;b' AS pair", db_path=db_path)
    assert result["rows"] == [["a;b"]]
    # A trailing semicolon is still a single statement.
    assert query_database("SELECT 1 AS one;", db_path=db_path)["rows"] == [[1]]


def test_cte_select_allowed(db_path: Path) -> None:
    """The authorizer allowlist must not be overtight: CTEs are legal reads."""
    plain = query_database(
        "WITH cte AS (SELECT 1 AS x) SELECT x FROM cte", db_path=db_path
    )
    assert plain["rows"] == [[1]]
    recursive = query_database(
        "WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq "
        "WHERE n < 5) SELECT n FROM seq",
        db_path=db_path,
    )
    assert [row[0] for row in recursive["rows"]] == [1, 2, 3, 4, 5]


def test_read_only_mode_engages_without_authorizer(db_path: Path) -> None:
    """Layer 1 alone (URI mode=ro) refuses writes even with no authorizer set."""
    ensure_database(db_path)
    connection = _connect_read_only(db_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("INSERT INTO companies VALUES (99, 'X', 'X', 'X')")
    finally:
        connection.close()


def test_row_cap_enforced(db_path: Path) -> None:
    result = query_database(
        "SELECT id FROM vacancies ORDER BY id", max_rows=3, db_path=db_path
    )
    assert result["row_count"] == 3
    assert result["truncated"] is True


def test_empty_sql_rejected(db_path: Path) -> None:
    with pytest.raises(ToolError, match="empty"):
        query_database("   ", db_path=db_path)
