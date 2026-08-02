"""Alembic smoke test for the first business migration."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

BACKEND_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "alembic_version",
    "jobs",
    "job_sources",
    "job_imports",
    "job_import_items",
}


def _run_alembic(database_url: str, *args: str) -> None:
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_first_business_migration_up_and_down(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path}"

    _run_alembic(database_url, "upgrade", "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == EXPECTED_TABLES
    assert {item["name"] for item in inspector.get_unique_constraints("jobs")} == {
        "uq_jobs_canonical_key"
    }
    assert {
        item["name"] for item in inspector.get_check_constraints("jobs")
    } >= {
        "remote_status_enum",
        "remote_confidence_enum",
        "ck_jobs_salary_range",
    }
    engine.dispose()

    _run_alembic(database_url, "downgrade", "base")

    engine = create_engine(database_url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
