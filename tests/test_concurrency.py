"""Concurrency tests: fire many tool calls at once and assert no shared-state
corruption. The tool functions are synchronous and each opens its own SQLite
connection / file handle, so the real risk is *shared* state -- module-level
caches, a reused connection, or the first-run seeder racing itself. We drive
them concurrently with ``asyncio.gather`` over ``asyncio.to_thread`` (true
thread parallelism for the blocking calls) and check every result is correct.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.tools.database import query_database
from app.tools.files import read_file
from app.tools.search import search_web


async def test_concurrent_queries_do_not_corrupt_each_other(rich_db_path: Path) -> None:
    # Failure: a shared connection/cursor being reused across calls, so
    # interleaved queries return each other's rows.
    async def count() -> int:
        result = await asyncio.to_thread(
            query_database, "SELECT COUNT(*) FROM vacancies", db_path=rich_db_path
        )
        return int(result["rows"][0][0])

    counts = await asyncio.gather(*[count() for _ in range(25)])
    assert counts == [21] * 25


async def test_concurrent_distinct_queries_return_own_results(rich_db_path: Path) -> None:
    # Failure: results bleeding between concurrent callers issuing *different*
    # queries at the same time.
    async def grade_count(grade: str) -> tuple[str, int]:
        result = await asyncio.to_thread(
            query_database,
            f"SELECT COUNT(*) FROM vacancies WHERE grade = '{grade}'",
            db_path=rich_db_path,
        )
        return grade, int(result["rows"][0][0])

    grades = ["junior", "middle", "senior", "lead"]
    pairs = await asyncio.gather(*[grade_count(g) for g in grades * 8])
    tally = {g: c for g, c in pairs}
    # Each grade always resolves to its own stable count, never another's.
    assert tally == {"junior": 4, "middle": 6, "senior": 7, "lead": 4}


async def test_concurrent_first_run_seeding_via_asyncio(tmp_path: Path) -> None:
    # Failure: the lazy first-run seeder racing itself under async fan-out
    # ("table already exists" / partial-DB reads) when the file does not exist yet.
    fresh = tmp_path / "async_race.db"

    async def seed_and_count() -> int:
        result = await asyncio.to_thread(
            query_database, "SELECT COUNT(*) FROM companies", db_path=fresh
        )
        return int(result["rows"][0][0])

    counts = await asyncio.gather(*[seed_and_count() for _ in range(20)])
    assert counts == [6] * 20  # every caller reads a fully-seeded database


async def test_concurrent_mixed_tools_are_independent(
    rich_db_path: Path, sandbox: Path, index_path: Path
) -> None:
    # Failure: cross-tool shared state (module globals) corrupting results when
    # search / read_file / query_database run interleaved.
    async def do_search() -> str:
        result = await asyncio.to_thread(
            search_web, "mcp transports", index_path=index_path
        )
        return result["source"]

    async def do_read() -> str:
        result = await asyncio.to_thread(read_file, "docs/notes.md", data_dir=sandbox)
        return result["content"]

    async def do_query() -> int:
        result = await asyncio.to_thread(
            query_database, "SELECT COUNT(*) FROM companies", db_path=rich_db_path
        )
        return int(result["rows"][0][0])

    tasks: list[asyncio.Future[object]] = []
    for _ in range(10):
        tasks.append(asyncio.ensure_future(do_search()))
        tasks.append(asyncio.ensure_future(do_read()))
        tasks.append(asyncio.ensure_future(do_query()))
    results = await asyncio.gather(*tasks)

    sources = results[0::3]
    contents = results[1::3]
    counts = results[2::3]
    assert sources == ["offline_index"] * 10
    assert all("hello from the sandbox" in c for c in contents)  # type: ignore[operator]
    assert counts == [12] * 10  # rich DB has 12 companies
