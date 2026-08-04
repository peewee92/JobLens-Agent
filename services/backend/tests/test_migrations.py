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
    "requirement_eval_reviews",
}
REQUIREMENT_REVIEW_BASE_TABLES = {
    "requirement_review_batches",
    "requirement_review_batch_cases",
    "requirement_review_case_reviews",
}
REQUIREMENT_REVIEW_FINAL_DECISION_TABLES = {
    "requirement_review_batch_final_decisions",
}
REQUIREMENT_REVIEW_TABLES = (
    REQUIREMENT_REVIEW_BASE_TABLES | REQUIREMENT_REVIEW_FINAL_DECISION_TABLES
)
REQUIREMENT_ACCEPTANCE_RUN_TABLES = {
    "requirement_acceptance_runs",
    "requirement_acceptance_run_cases",
}
REQUIREMENT_ACCEPTANCE_LEASE_TABLES = {
    "requirement_acceptance_execution_leases",
}
REQUIREMENT_ACCEPTANCE_TABLES = (
    REQUIREMENT_ACCEPTANCE_RUN_TABLES
    | REQUIREMENT_ACCEPTANCE_LEASE_TABLES
    | {"requirement_acceptance_canary_reviews"}
)
EXPECTED_TABLES = (
    JOB_TABLES
    | CAREER_CONTEXT_TABLES
    | TRACE_TABLES
    | PROFILE_EVAL_TABLES
    | JOB_REQUIREMENT_TABLES
    | REQUIREMENT_EVAL_TABLES
    | REQUIREMENT_REVIEW_TABLES
    | REQUIREMENT_ACCEPTANCE_TABLES
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
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("requirement_eval_reviews")
    } == {"uq_requirement_eval_reviews_eval_run_id"}
    assert {
        item["name"]
        for item in inspector.get_check_constraints("requirement_eval_reviews")
    } >= {"ck_requirement_eval_reviews_decision"}
    requirement_eval_review_columns = {
        item["name"]: item for item in inspector.get_columns("requirement_eval_reviews")
    }
    assert requirement_eval_review_columns["eval_run_id"]["type"].length == 90
    requirement_eval_review_foreign_keys = inspector.get_foreign_keys(
        "requirement_eval_reviews"
    )
    assert any(
        item["constrained_columns"] == ["eval_run_id"]
        and item["referred_table"] == "requirement_eval_runs"
        for item in requirement_eval_review_foreign_keys
    )
    requirement_eval_case_foreign_keys = inspector.get_foreign_keys(
        "requirement_eval_case_results"
    )
    assert any(
        item["constrained_columns"] == ["trace_run_id"]
        and item["referred_table"] == "trace_spans"
        for item in requirement_eval_case_foreign_keys
    )
    assert {
        item["name"]
        for item in inspector.get_check_constraints("requirement_review_batches")
    } >= {"ck_requirement_review_batches_sample_size"}
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("requirement_review_batch_cases")
    } == {
        "uq_requirement_review_cases_batch_index",
        "uq_requirement_review_cases_batch_extraction",
    }
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("requirement_review_case_reviews")
    } == {"uq_requirement_review_case_reviews_case"}
    assert {
        item["name"]
        for item in inspector.get_check_constraints("requirement_review_case_reviews")
    } >= {"ck_requirement_review_case_reviews_decision"}
    assert {
        item["name"]
        for item in inspector.get_unique_constraints(
            "requirement_review_batch_final_decisions"
        )
    } == {"uq_requirement_review_batch_final_decisions_batch"}
    assert {
        item["name"]
        for item in inspector.get_check_constraints(
            "requirement_review_batch_final_decisions"
        )
    } >= {
        "ck_requirement_review_batch_final_decisions_decision",
        "ck_requirement_review_batch_final_decisions_counts_non_negative",
        "ck_requirement_review_batch_final_decisions_reviewed_count",
    }
    final_decision_foreign_keys = inspector.get_foreign_keys(
        "requirement_review_batch_final_decisions"
    )
    assert any(
        item["constrained_columns"] == ["batch_id"]
        and item["referred_table"] == "requirement_review_batches"
        for item in final_decision_foreign_keys
    )
    assert {
        item["name"]
        for item in inspector.get_indexes(
            "requirement_review_batch_final_decisions"
        )
    } >= {"ix_requirement_review_batch_final_decisions_decision_decided_at"}
    review_case_foreign_keys = inspector.get_foreign_keys(
        "requirement_review_batch_cases"
    )
    assert any(
        item["constrained_columns"] == ["extraction_id", "job_id"]
        and item["referred_table"] == "job_requirement_extractions"
        for item in review_case_foreign_keys
    )
    extraction_foreign_keys = inspector.get_foreign_keys(
        "job_requirement_extractions"
    )
    assert any(
        item["constrained_columns"] == ["job_id"]
        and item["referred_table"] == "jobs"
        for item in extraction_foreign_keys
    )
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("requirement_acceptance_runs")
    } == {"uq_requirement_acceptance_runs_identity"}
    assert {
        item["name"]
        for item in inspector.get_check_constraints("requirement_acceptance_runs")
    } >= {"ck_requirement_acceptance_runs_formal_sample_size"}
    assert {
        item["name"]
        for item in inspector.get_unique_constraints(
            "requirement_acceptance_run_cases"
        )
    } == {
        "uq_requirement_acceptance_run_cases_index",
        "uq_requirement_acceptance_run_cases_source_url",
    }
    assert {
        item["name"]
        for item in inspector.get_check_constraints(
            "requirement_acceptance_run_cases"
        )
    } >= {
        "ck_requirement_acceptance_run_cases_index",
        "ck_requirement_acceptance_run_cases_status",
        "ck_requirement_acceptance_run_cases_attempt_count",
    }
    acceptance_case_columns = {
        item["name"]: item
        for item in inspector.get_columns("requirement_acceptance_run_cases")
    }
    assert "description_snapshot" in acceptance_case_columns
    assert acceptance_case_columns["description_snapshot"]["nullable"] is True
    acceptance_case_foreign_keys = inspector.get_foreign_keys(
        "requirement_acceptance_run_cases"
    )
    assert any(
        item["constrained_columns"] == ["run_id"]
        and item["referred_table"] == "requirement_acceptance_runs"
        for item in acceptance_case_foreign_keys
    )
    assert any(
        item["constrained_columns"] == ["trace_run_id"]
        and item["referred_table"] == "trace_spans"
        for item in acceptance_case_foreign_keys
    )
    assert any(
        item["constrained_columns"] == ["extraction_id"]
        and item["referred_table"] == "job_requirement_extractions"
        for item in acceptance_case_foreign_keys
    )
    assert {
        item["name"]
        for item in inspector.get_unique_constraints(
            "requirement_acceptance_canary_reviews"
        )
    } == {"uq_requirement_acceptance_canary_reviews_run_id"}
    assert {
        item["name"]
        for item in inspector.get_check_constraints(
            "requirement_acceptance_canary_reviews"
        )
    } >= {"ck_requirement_acceptance_canary_reviews_decision"}
    canary_foreign_keys = inspector.get_foreign_keys(
        "requirement_acceptance_canary_reviews"
    )
    assert any(
        item["constrained_columns"] == ["run_id"]
        and item["referred_table"] == "requirement_acceptance_runs"
        for item in canary_foreign_keys
    )
    assert {
        item["name"]
        for item in inspector.get_check_constraints(
            "requirement_acceptance_execution_leases"
        )
    } >= {"ck_requirement_acceptance_execution_leases_expiry"}
    assert {
        item["name"]
        for item in inspector.get_indexes("requirement_acceptance_execution_leases")
    } >= {"ix_requirement_acceptance_execution_leases_expires_at"}
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260805_0014")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == (
        EXPECTED_TABLES - REQUIREMENT_REVIEW_FINAL_DECISION_TABLES
    )
    engine.dispose()

    _run_alembic(database_url, "upgrade", "head")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260804_0013")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == (
        EXPECTED_TABLES
        - REQUIREMENT_ACCEPTANCE_LEASE_TABLES
        - REQUIREMENT_REVIEW_FINAL_DECISION_TABLES
    )
    columns_at_0013 = {
        item["name"]
        for item in inspector.get_columns("requirement_acceptance_run_cases")
    }
    assert "description_snapshot" in columns_at_0013
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260804_0012")

    engine = create_engine(database_url)
    downgraded_columns = {
        item["name"]
        for item in inspect(engine).get_columns("requirement_acceptance_run_cases")
    }
    assert "description_snapshot" not in downgraded_columns
    assert set(inspect(engine).get_table_names()) == (
        EXPECTED_TABLES
        - REQUIREMENT_ACCEPTANCE_LEASE_TABLES
        - REQUIREMENT_REVIEW_FINAL_DECISION_TABLES
    )
    engine.dispose()

    _run_alembic(database_url, "upgrade", "head")

    engine = create_engine(database_url)
    upgraded_columns = {
        item["name"]
        for item in inspect(engine).get_columns("requirement_acceptance_run_cases")
    }
    assert "description_snapshot" in upgraded_columns
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260804_0011")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == (
        EXPECTED_TABLES
        - REQUIREMENT_ACCEPTANCE_LEASE_TABLES
        - REQUIREMENT_REVIEW_FINAL_DECISION_TABLES
        - {"requirement_acceptance_canary_reviews"}
    )
    engine.dispose()

    _run_alembic(database_url, "upgrade", "head")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260803_0009")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == (
        JOB_TABLES
        | CAREER_CONTEXT_TABLES
        | TRACE_TABLES
        | PROFILE_EVAL_TABLES
        | JOB_REQUIREMENT_TABLES
        | REQUIREMENT_EVAL_TABLES
    )
    engine.dispose()

    _run_alembic(database_url, "downgrade", "20260803_0008")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == (
        JOB_TABLES
        | CAREER_CONTEXT_TABLES
        | TRACE_TABLES
        | PROFILE_EVAL_TABLES
        | JOB_REQUIREMENT_TABLES
        | {"requirement_eval_runs", "requirement_eval_case_results"}
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
