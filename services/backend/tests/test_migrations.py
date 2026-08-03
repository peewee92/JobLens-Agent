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
TRACE_TABLES = {"trace_spans"}
PROFILE_EVAL_TABLES = {
    "profile_eval_runs",
    "profile_eval_case_results",
    "profile_eval_reviews",
}
JOB_REQUIREMENT_TABLES = {
    "job_requirement_extractions",
    "job_requirements",
}
REQUIREMENT_EVAL_TABLES = {
    "requirement_eval_runs",
    "requirement_eval_case_results",
}
EXPECTED_TABLES = (
    JOB_TABLES
    | CAREER_CONTEXT_TABLES
    | TRACE_TABLES
    | PROFILE_EVAL_TABLES
    | JOB_REQUIREMENT_TABLES
    | REQUIREMENT_EVAL_TABLES
)


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
    assert {
        item["name"] for item in inspector.get_check_constraints("trace_spans")
    } >= {
        "ck_trace_spans_latency_non_negative",
        "ck_trace_spans_input_tokens_non_negative",
        "ck_trace_spans_output_tokens_non_negative",
    }
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("profile_eval_case_results")
    } == {"uq_profile_eval_case_run_case"}
    assert {
        item["name"]
        for item in inspector.get_check_constraints("profile_eval_runs")
    } >= {
        "ck_profile_eval_runs_case_rate_range",
        "ck_profile_eval_runs_workflow_rate_range",
        "ck_profile_eval_runs_skill_recall_range",
        "ck_profile_eval_runs_forbidden_rate_range",
        "ck_profile_eval_runs_mode",
        "ck_profile_eval_runs_release_eligibility",
    }
    baseline_foreign_keys = inspector.get_foreign_keys("profile_eval_runs")
    assert any(
        item["constrained_columns"] == ["baseline_run_id"]
        and item["referred_table"] == "profile_eval_runs"
        for item in baseline_foreign_keys
    )
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("profile_eval_reviews")
    } == {"uq_profile_eval_reviews_eval_run_id"}
    assert {
        item["name"]
        for item in inspector.get_check_constraints("profile_eval_reviews")
    } >= {"ck_profile_eval_reviews_decision"}
    review_foreign_keys = inspector.get_foreign_keys("profile_eval_reviews")
    assert any(
        item["constrained_columns"] == ["eval_run_id"]
        and item["referred_table"] == "profile_eval_runs"
        for item in review_foreign_keys
    )
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("job_requirements")
    } == {"uq_job_requirements_extraction_index"}
    assert {
        item["name"]
        for item in inspector.get_check_constraints("job_requirements")
    } >= {
        "ck_job_requirements_index_non_negative",
        "ck_job_requirements_type",
        "ck_job_requirements_importance",
        "ck_job_requirements_confidence_range",
    }
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("requirement_eval_case_results")
    } == {"uq_requirement_eval_case_run_case"}
    assert {
        item["name"]
        for item in inspector.get_check_constraints("requirement_eval_runs")
    } >= {
        "ck_requirement_eval_runs_case_rate_range",
        "ck_requirement_eval_runs_workflow_rate_range",
        "ck_requirement_eval_runs_capability_recall_range",
        "ck_requirement_eval_runs_importance_accuracy_range",
        "ck_requirement_eval_runs_forbidden_rate_range",
        "ck_requirement_eval_runs_mode",
        "ck_requirement_eval_runs_release_eligibility",
    }
    requirement_eval_foreign_keys = inspector.get_foreign_keys(
        "requirement_eval_runs"
    )
    assert any(
        item["constrained_columns"] == ["baseline_run_id"]
        and item["referred_table"] == "requirement_eval_runs"
        for item in requirement_eval_foreign_keys
    )
    requirement_eval_case_foreign_keys = inspector.get_foreign_keys(
        "requirement_eval_case_results"
    )
    assert any(
        item["constrained_columns"] == ["trace_run_id"]
        and item["referred_table"] == "trace_spans"
        for item in requirement_eval_case_foreign_keys
    )
    extraction_foreign_keys = inspector.get_foreign_keys(
        "job_requirement_extractions"
    )
    assert any(
        item["constrained_columns"] == ["job_id"]
        and item["referred_table"] == "jobs"
        for item in extraction_foreign_keys
    )
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260803_0007")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == (
        JOB_TABLES
        | CAREER_CONTEXT_TABLES
        | TRACE_TABLES
        | PROFILE_EVAL_TABLES
        | JOB_REQUIREMENT_TABLES
    )
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260803_0006")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == (
        JOB_TABLES | CAREER_CONTEXT_TABLES | TRACE_TABLES | PROFILE_EVAL_TABLES
    )
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260803_0005")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == (
        JOB_TABLES | CAREER_CONTEXT_TABLES | TRACE_TABLES
        | {"profile_eval_runs", "profile_eval_case_results"}
    )
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260803_0004")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == (
        JOB_TABLES | CAREER_CONTEXT_TABLES | TRACE_TABLES
    )
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260803_0003")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == (
        JOB_TABLES | CAREER_CONTEXT_TABLES
    )
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
