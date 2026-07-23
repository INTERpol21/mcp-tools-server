"""Tests for the read-only SQL tool and the demo database seeder."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from app.core.errors import ToolError
from app.tools.database import (
    HARD_ROW_CAP,
    MAX_CELL_BYTES,
    MAX_SQL_CHARS,
    _connect_read_only,
    query_database,
)
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


# --------------------------------------------------------------------------- #
# Hostile-input hardening (adversarial regression tests)
# --------------------------------------------------------------------------- #


def test_oversized_sql_rejected(db_path: Path) -> None:
    ensure_database(db_path)
    huge = "SELECT " + " OR ".join(["1=1"] * 12000)  # ~84 KB
    assert len(huge) > MAX_SQL_CHARS
    with pytest.raises(ToolError, match="too long"):
        query_database(huge, db_path=db_path)


def test_deeply_nested_select_surfaces_clean_toolerror(db_path: Path) -> None:
    """SQLite's own depth/parser limit must surface as a ToolError, not a crash."""
    ensure_database(db_path)
    sql = "SELECT " + "(SELECT " * 1000 + "1" + ")" * 1000
    assert len(sql) <= MAX_SQL_CHARS  # passes the length gate; sqlite rejects it
    with pytest.raises(ToolError) as excinfo:
        query_database(sql, db_path=db_path)
    assert "Traceback" not in str(excinfo.value)


def test_single_huge_blob_cell_is_refused(db_path: Path) -> None:
    """A row conjuring a huge blob is refused; the row-count cap alone would
    let a single oversized cell through."""
    ensure_database(db_path)
    with pytest.raises(ToolError, match="too large"):
        query_database(f"SELECT randomblob({MAX_CELL_BYTES + 1000})", db_path=db_path)


def test_small_blob_is_summarised_not_crashing(db_path: Path) -> None:
    ensure_database(db_path)
    result = query_database("SELECT zeroblob(10) AS b", db_path=db_path)
    assert result["rows"] == [["<blob: 10 bytes>"]]


def test_unicode_identifier_is_handled(db_path: Path) -> None:
    ensure_database(db_path)
    result = query_database('SELECT 1 AS "столбец"', db_path=db_path)
    assert result["columns"] == ["столбец"]
    assert result["rows"] == [[1]]


def test_comment_only_and_bare_semicolons_rejected(db_path: Path) -> None:
    ensure_database(db_path)
    with pytest.raises(ToolError, match="no result set"):
        query_database("-- just a comment", db_path=db_path)
    with pytest.raises(ToolError, match="[Mm]ultiple"):
        query_database(";;;", db_path=db_path)


def test_concurrent_first_run_seeding_is_race_safe(tmp_path: Path) -> None:
    """10 threads querying an unseeded database must all seed/read cleanly:
    no 'table already exists' collision, no partial-db reads."""
    fresh = tmp_path / "race.db"
    results: list[int] = []
    errors: list[str] = []

    def worker() -> None:
        try:
            result = query_database("SELECT COUNT(*) FROM companies", db_path=fresh)
            results.append(result["rows"][0][0])
        except Exception as exc:  # noqa: BLE001 - we assert there are none
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert results == [6] * 10


# --------------------------------------------------------------------------- #
# More adversarial hardening, exercised against the rich fixture DB.
# Each test names the concrete production failure it guards against.
# --------------------------------------------------------------------------- #


def test_null_values_serialise_as_none(db_path: Path) -> None:
    # Failure: a NULL cell crashing JSON serialisation or being dropped silently.
    result = query_database("SELECT NULL AS n, 1 AS one", db_path=db_path)
    assert result["rows"] == [[None, 1]]


def test_hard_row_cap_bounds_result_regardless_of_max_rows(db_path: Path) -> None:
    # Failure: an unbounded result set flooding the model context; max_rows above
    # HARD_ROW_CAP must not lift the ceiling, even for a generative CTE.
    ensure_database(db_path)
    sql = (
        "WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq "
        "WHERE n < 5000) SELECT n FROM seq"
    )
    result = query_database(sql, max_rows=1_000_000, db_path=db_path)
    assert result["row_count"] == HARD_ROW_CAP
    assert result["truncated"] is True


@pytest.mark.parametrize(
    "sql",
    [
        "PRAGMA table_info(companies)",  # statement-form pragma
        "SELECT name FROM pragma_table_info('companies')",  # function-form pragma
        "SELECT load_extension('/tmp/evil.so')",  # code-loading side channel
    ],
)
def test_pragma_and_extension_side_channels_rejected(db_path: Path, sql: str) -> None:
    # Failure: schema enumeration / arbitrary code loading slipping past the
    # SELECT-only guard through PRAGMA or load_extension.
    ensure_database(db_path)
    with pytest.raises(ToolError, match="read-only"):
        query_database(sql, db_path=db_path)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT FROM WHERE",  # garbled syntax
        "SELECT * FROM no_such_table",  # unknown table
        "SELECT no_such_column FROM companies",  # unknown column
    ],
)
def test_malformed_sql_returns_clean_toolerror_not_crash(db_path: Path, sql: str) -> None:
    # Failure: a SQL error leaking a raw traceback to the caller instead of one
    # clean structured line.
    ensure_database(db_path)
    with pytest.raises(ToolError) as excinfo:
        query_database(sql, db_path=db_path)
    message = str(excinfo.value)
    assert message.startswith("SQL error:")
    assert "Traceback" not in message


def test_unicode_and_emoji_table_data_round_trips(rich_db_path: Path) -> None:
    # Failure: mojibake / encoding loss on Cyrillic, CJK and emoji stored in the DB.
    result = query_database(
        "SELECT name, city FROM companies WHERE id IN (2, 3, 5) ORDER BY id",
        db_path=rich_db_path,
    )
    assert result["rows"] == [
        ["Ёлка Софт", "Санкт-Петербург"],
        ["日本テック", "東京"],
        ["Rocket 🚀 Labs", "Baikonur"],
    ]


def test_large_integer_salary_preserved(rich_db_path: Path) -> None:
    # Failure: a large integer being truncated or coerced to float in transit.
    result = query_database(
        "SELECT salary_rub FROM vacancies WHERE id = 21", db_path=rich_db_path
    )
    assert result["rows"] == [[9_999_999]]


def test_semicolon_inside_stored_data_is_not_a_statement_boundary(rich_db_path: Path) -> None:
    # Failure: a ';' inside stored/column data being mistaken for a statement
    # separator and rejected as multi-statement.
    result = query_database(
        "SELECT stack FROM vacancies WHERE stack LIKE '%;%'", db_path=rich_db_path
    )
    assert result["rows"] == [["Go, eBPF, Rust; ATT&CK"]]


def test_pagination_is_deterministic(rich_db_path: Path) -> None:
    # Failure: unstable ordering across LIMIT/OFFSET pages causing rows to be
    # skipped or duplicated when a client paginates.
    page_sql = "SELECT id FROM vacancies ORDER BY id LIMIT 5 OFFSET {offset}"
    seen: list[int] = []
    for offset in (0, 5, 10, 15, 20):
        page = query_database(page_sql.format(offset=offset), db_path=rich_db_path)
        seen.extend(row[0] for row in page["rows"])
    assert seen == list(range(1, 22))  # 21 vacancies, no gaps, no repeats


@pytest.mark.parametrize("max_rows", [0, -5])
def test_nonpositive_max_rows_clamped_to_at_least_one(db_path: Path, max_rows: int) -> None:
    # Failure: max_rows<=0 yielding an empty or error result instead of one row.
    ensure_database(db_path)
    result = query_database(
        "SELECT id FROM companies ORDER BY id", max_rows=max_rows, db_path=db_path
    )
    assert result["row_count"] == 1
    assert result["truncated"] is True


def test_unavailable_database_hides_server_paths(tmp_path: Path) -> None:
    """Seeding/connect failures must become a clean ToolError, not leak the
    absolute server-side path from a raw OSError / sqlite3.OperationalError."""
    # A file where the parent directory should be makes mkdir/seed fail.
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory")
    bad_path = blocker / "nested" / "demo.db"

    with pytest.raises(ToolError) as err:
        query_database("SELECT 1", 5, db_path=bad_path)
    message = str(err.value)
    assert str(tmp_path) not in message
    assert "demo.db" not in message
