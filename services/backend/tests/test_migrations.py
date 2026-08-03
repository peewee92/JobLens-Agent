"""Alembic smoke test for the first business migration."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

BACKEND_ROOT = Path(__file__).resolve().parents[1]
BASE_TABLES = {
    "alembic_version",
    "jobs",
    "job_sources",
    "job_imports",
    "job_import_items",
}
JOB_TABLES = BASE_TABLES | {"job_import_candidates"}
CAREER_CONTEXT_TABLES = {
    "user_profiles",
    "profile_evidence",
    "profile_skills",
    "profile_skill_evidence",
    "search_intents",
}
EXPECTED_TABLES = JOB_TABLES | CAREER_CONTEXT_TABLES


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
        item["name"]
        for item in inspector.get_unique_constraints("job_import_candidates")
    } == {"uq_job_import_candidates_import_candidate_index"}
    assert {
        item["name"]
        for item in inspector.get_check_constraints("job_import_candidates")
    } >= {"ck_job_import_candidates_index_non_negative"}
    assert {
        item["name"] for item in inspector.get_check_constraints("jobs")
    } >= {
        "remote_status_enum",
        "remote_confidence_enum",
        "ck_jobs_salary_range",
    }
    assert {
        item["name"] for item in inspector.get_unique_constraints("user_profiles")
    } == {"uq_user_profiles_key_version"}
    assert {
        item["name"] for item in inspector.get_unique_constraints("search_intents")
    } == {"uq_search_intents_key_version"}
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260802_0002")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == JOB_TABLES
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260801_0001")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == BASE_TABLES
    engine.dispose()

    _run_alembic(database_url, "downgrade", "base")

    engine = create_engine(database_url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
