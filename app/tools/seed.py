"""Idempotent seeding of the bundled demo SQLite database.

The database file is intentionally NOT committed to git: it is generated on
demand, either explicitly (``python -m app.tools.seed`` / ``make seed``) or
lazily on the first ``query_database`` call.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    industry TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE vacancies (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    title TEXT NOT NULL,
    grade TEXT NOT NULL CHECK (grade IN ('junior', 'middle', 'senior', 'lead')),
    salary_rub INTEGER NOT NULL,
    stack TEXT NOT NULL
);

CREATE TABLE applications (
    id INTEGER PRIMARY KEY,
    vacancy_id INTEGER NOT NULL REFERENCES vacancies(id),
    applied_at TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('applied', 'screening', 'interview', 'offer', 'rejected'))
);
"""

_COMPANIES: list[tuple[int, str, str, str]] = [
    (1, "Aurora Labs", "AI Platform", "Moscow"),
    (2, "FinPeak", "Fintech", "Saint Petersburg"),
    (3, "CloudMesh", "Cloud Infrastructure", "Novosibirsk"),
    (4, "RetailHub", "E-commerce", "Moscow"),
    (5, "MediData", "HealthTech", "Kazan"),
    (6, "GameSpark", "GameDev", "Remote"),
]

_VACANCIES: list[tuple[int, int, str, str, int, str]] = [
    (1, 1, "Senior Fullstack Engineer", "senior", 320000, "TypeScript, React, Node.js, PostgreSQL"),
    (2, 1, "ML Platform Engineer", "senior", 350000, "Python, FastAPI, Kubernetes, MLflow"),
    (3, 2, "Backend Developer", "middle", 240000, "Python, Django, PostgreSQL, Redis"),
    (4, 2, "Frontend Developer", "middle", 220000, "React, TypeScript, Vite"),
    (5, 3, "DevOps Engineer", "senior", 300000, "Kubernetes, Terraform, AWS, Go"),
    (6, 3, "Site Reliability Engineer", "middle", 260000, "Prometheus, Grafana, Python"),
    (7, 4, "Fullstack Developer", "middle", 230000, "PHP, Laravel, Vue.js, MySQL"),
    (8, 4, "Data Engineer", "senior", 310000, "Python, Airflow, ClickHouse, Kafka"),
    (9, 5, "Python Developer", "junior", 140000, "Python, FastAPI, PostgreSQL"),
    (10, 6, "Unity Developer", "middle", 250000, "C#, Unity, Photon"),
]

_APPLICATIONS: list[tuple[int, int, str, str]] = [
    (1, 1, "2026-06-02", "interview"),
    (2, 2, "2026-06-03", "screening"),
    (3, 3, "2026-06-05", "rejected"),
    (4, 5, "2026-06-08", "offer"),
    (5, 7, "2026-06-10", "applied"),
    (6, 8, "2026-06-11", "interview"),
    (7, 9, "2026-06-12", "applied"),
    (8, 10, "2026-06-15", "screening"),
    (9, 4, "2026-06-16", "applied"),
]


def ensure_database(db_path: Path) -> bool:
    """Create and seed the demo database if it does not exist yet.

    Idempotent: an existing file is left untouched. A partially written file
    is removed on failure so the next call can start clean.

    Returns:
        True if the database was created, False if it already existed.
    """
    if db_path.exists():
        return False
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.executescript(_SCHEMA)
            connection.executemany(
                "INSERT INTO companies VALUES (?, ?, ?, ?)", _COMPANIES
            )
            connection.executemany(
                "INSERT INTO vacancies VALUES (?, ?, ?, ?, ?, ?)", _VACANCIES
            )
            connection.executemany(
                "INSERT INTO applications VALUES (?, ?, ?, ?)", _APPLICATIONS
            )
    except BaseException:
        db_path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()
    return True


def main() -> None:
    """CLI entry point: ``python -m app.tools.seed``."""
    from app.config import load_settings

    settings = load_settings()
    created = ensure_database(settings.db_path)
    state = "seeded" if created else "already present"
    print(f"Demo database {state}: {settings.db_path}")


if __name__ == "__main__":
    main()
