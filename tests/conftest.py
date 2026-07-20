"""Shared fixtures: repository paths, a sandboxed data directory, and a rich DB.

The ``rich_db_path`` fixture below builds a larger, deliberately messy demo
database (unicode, emoji, salary/edge values, every grade and status) in an
isolated ``tmp_path`` file. It reuses the production schema from
``app.tools.seed`` verbatim, so the fixture can never drift from the real
schema, yet the checked-in ``data/demo.db`` is never touched and the existing
6-company ``db_path`` tests keep passing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.tools.seed import _SCHEMA

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def index_path() -> Path:
    """The committed offline search index (deterministic test data)."""
    return REPO_ROOT / "data" / "search_index.json"


# --------------------------------------------------------------------------- #
# Rich demo-database fixture
#
# A superset of the production seed: same three tables, many more rows, and
# intentionally adversarial content that a naive tool would mishandle --
# Cyrillic / CJK / accented / emoji text, ';' and quotes embedded in data,
# the salary extremes (0 and a very large integer), and every CHECK-allowed
# grade ('junior'..'lead') and status ('applied'..'rejected'). Anchor rows
# are called out so tests can assert on exact, stable values.
# --------------------------------------------------------------------------- #

# companies(id, name, industry, city)
RICH_COMPANIES: list[tuple[int, str, str, str]] = [
    (1, "Aurora Labs", "AI Platform", "Moscow"),          # ASCII anchor
    (2, "Ёлка Софт", "Fintech", "Санкт-Петербург"),        # Cyrillic anchor
    (3, "日本テック", "Robotics", "東京"),                    # CJK anchor
    (4, "Café Données", "Data", "Montréal"),               # accented Latin
    (5, "Rocket 🚀 Labs", "Space", "Baikonur"),            # emoji in name
    (6, "O'Really Systems", "Publishing", "Dublin"),       # apostrophe in name
    (7, "Semi;Colon Inc", "Security", "Berlin"),           # ';' inside data
    (8, "CloudMesh", "Cloud Infrastructure", "Novosibirsk"),
    (9, "RetailHub", "E-commerce", "Moscow"),
    (10, "MediData", "HealthTech", "Kazan"),
    (11, "GameSpark", "GameDev", "Remote"),
    (12, "Quantum Knits", "Manufacturing", "Remote"),      # matches nothing in search index
]

# vacancies(id, company_id, title, grade, salary_rub, stack)
# grade CHECK: junior|middle|senior|lead ; every value appears at least once.
RICH_VACANCIES: list[tuple[int, int, str, str, int, str]] = [
    (1, 1, "Senior Fullstack Engineer", "senior", 320000, "TypeScript, React, Node.js"),
    (2, 1, "ML Platform Engineer", "lead", 420000, "Python, FastAPI, Kubernetes, MLflow"),
    (3, 2, "Бэкенд-разработчик", "middle", 240000, "Python, Django, PostgreSQL"),   # Cyrillic title
    (4, 2, "Frontend Developer", "junior", 150000, "React, TypeScript, Vite"),
    (5, 3, "ロボティクス・エンジニア", "senior", 300000, "C++, ROS, Rust"),          # CJK title
    (6, 3, "Firmware Engineer", "middle", 260000, "C, Zephyr, Python"),
    (7, 4, "Data Engineer", "senior", 310000, "Python, Airflow, ClickHouse"),
    (8, 4, "Analytics Lead", "lead", 400000, "SQL, dbt, Looker"),
    (9, 5, "Guidance Engineer 🚀", "senior", 500000, "C++, MATLAB, Kalman"),  # emoji in title
    (10, 5, "Intern", "junior", 0, "Python"),  # salary edge: 0
    (11, 6, "Editor Tooling Dev", "middle", 230000, "Ruby, Rails"),
    (12, 7, "Security Engineer", "senior", 330000, "Go, eBPF, Rust; ATT&CK"),  # ';' in stack
    (13, 8, "DevOps Engineer", "senior", 300000, "Kubernetes, Terraform, AWS"),
    (14, 8, "SRE", "middle", 260000, "Prometheus, Grafana, Python"),
    (15, 9, "Fullstack Developer", "middle", 230000, "PHP, Laravel, Vue.js"),
    (16, 9, "Staff Engineer", "lead", 450000, "Java, Kotlin, Spring"),
    (17, 10, "Python Developer", "junior", 140000, "Python, FastAPI"),
    (18, 11, "Unity Developer", "middle", 250000, "C#, Unity, Photon"),
    (19, 11, "Graphics Programmer", "senior", 340000, "C++, Vulkan, HLSL"),
    (20, 12, "Loom Operator", "junior", 90000, "PLC, Ladder Logic"),
    # A very large but valid salary to exercise big-integer handling end to end.
    (21, 1, "Distinguished Engineer", "lead", 9_999_999, "Everything"),
]

# applications(id, vacancy_id, applied_at, status)
# status CHECK: applied|screening|interview|offer|rejected ; all five appear.
RICH_APPLICATIONS: list[tuple[int, int, str, str]] = [
    (1, 1, "2026-06-02", "interview"),
    (2, 2, "2026-06-03", "screening"),
    (3, 3, "2026-06-05", "rejected"),
    (4, 5, "2026-06-08", "offer"),
    (5, 7, "2026-06-10", "applied"),
    (6, 8, "2026-06-11", "interview"),
    (7, 9, "2026-06-12", "applied"),
    (8, 10, "2026-06-15", "screening"),
    (9, 4, "2026-06-16", "applied"),
    (10, 12, "2026-06-17", "rejected"),
    (11, 13, "2026-06-18", "offer"),
    (12, 16, "2026-06-19", "interview"),
    (13, 19, "2026-06-20", "screening"),
    (14, 21, "2026-06-21", "applied"),
    (15, 6, "2026-06-22", "rejected"),
]


def _build_rich_db(db_path: Path) -> None:
    """Materialise the rich dataset into ``db_path`` using the production schema."""
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.executescript(_SCHEMA)
            connection.executemany(
                "INSERT INTO companies VALUES (?, ?, ?, ?)", RICH_COMPANIES
            )
            connection.executemany(
                "INSERT INTO vacancies VALUES (?, ?, ?, ?, ?, ?)", RICH_VACANCIES
            )
            connection.executemany(
                "INSERT INTO applications VALUES (?, ?, ?, ?)", RICH_APPLICATIONS
            )
    finally:
        connection.close()


@pytest.fixture()
def rich_db_path(tmp_path: Path) -> Path:
    """An isolated, richly-seeded demo DB (same schema, more rows, unicode/edge data).

    Because the file already exists on disk, ``query_database`` -> ``ensure_database``
    leaves it untouched, so tests read this exact dataset. Nothing here mutates the
    committed ``data/demo.db``.
    """
    db_file = tmp_path / "rich_demo.db"
    _build_rich_db(db_file)
    return db_file


@pytest.fixture()
def sandbox(tmp_path: Path) -> Path:
    """A data directory with sample files, plus a secret outside of it."""
    data_dir = tmp_path / "data"
    docs = data_dir / "docs"
    docs.mkdir(parents=True)
    (docs / "notes.md").write_text("# Notes\nhello from the sandbox\n", encoding="utf-8")
    (docs / "pipeline.md").write_text(
        "# Pipeline\nretrieve -> rerank -> generate\n", encoding="utf-8"
    )
    (data_dir / "top.txt").write_text("top-level file\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("do not read me\n", encoding="utf-8")
    return data_dir


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Location for a throwaway demo database (seeded on demand)."""
    return tmp_path / "demo.db"
