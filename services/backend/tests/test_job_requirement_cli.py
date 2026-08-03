"""Process-level verification for the persisted Requirement Eval CLI."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    RequirementEvalCaseResultORM,
    RequirementEvalRunORM,
    TraceSpanORM,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _environment(tmp_path: Path, filename: str, provider: str) -> tuple[str, dict[str, str]]:
    database_url = f"sqlite+pysqlite:///{tmp_path / filename}"
    return database_url, {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "REQUIREMENT_EXTRACTOR_PROVIDER": provider,
    }


def _migrate(env: dict[str, str]) -> None:
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert migration.returncode == 0, migration.stdout + migration.stderr


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.run_requirement_eval", *args],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fixture_requirement_eval_cli_persists_run_cases_and_traces(
    tmp_path: Path,
) -> None:
    database_url, env = _environment(
        tmp_path,
        "requirement-eval-cli.db",
        "fixture",
    )
    _migrate(env)

    result = _run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Requirement Eval id=reqeval_" in result.stdout
    assert "passed=10/10" in result.stdout
    assert "capabilityRecall=100.00%" in result.stdout
    assert "importanceAccuracy=100.00%" in result.stdout
    assert "gatePassed=True" in result.stdout
    assert "releaseEligible=False" in result.stdout
    assert "does not qualify a live model" in result.stdout

    engine = create_engine(database_url)
    with Session(engine) as session:
        assert int(
            session.scalar(
                select(func.count())
                .select_from(TraceSpanORM)
                .where(TraceSpanORM.capability == "requirement_extraction")
            )
            or 0
        ) == 10
        assert int(
            session.scalar(select(func.count()).select_from(RequirementEvalRunORM))
            or 0
        ) == 1
        assert int(
            session.scalar(
                select(func.count()).select_from(RequirementEvalCaseResultORM)
            )
            or 0
        ) == 10
        run = session.scalar(select(RequirementEvalRunORM))
        assert run is not None
        assert run.mode == "fixture"
        assert run.release_eligible is False
    engine.dispose()


def test_requirement_eval_cli_compares_against_explicit_baseline(
    tmp_path: Path,
) -> None:
    database_url, env = _environment(
        tmp_path,
        "requirement-eval-baseline.db",
        "fixture",
    )
    _migrate(env)
    baseline_result = _run(env)
    assert baseline_result.returncode == 0, baseline_result.stdout + baseline_result.stderr

    engine = create_engine(database_url)
    with Session(engine) as session:
        baseline_id = session.scalar(select(RequirementEvalRunORM.id))
    assert baseline_id is not None

    current_result = _run(env, "--baseline-run-id", baseline_id)

    assert current_result.returncode == 0, current_result.stdout + current_result.stderr
    assert f"Baseline {baseline_id}:" in current_result.stdout
    assert "capabilityRecallDelta=+0.00%" in current_result.stdout
    with Session(engine) as session:
        assert int(
            session.scalar(select(func.count()).select_from(RequirementEvalRunORM))
            or 0
        ) == 2
        current = session.scalar(
            select(RequirementEvalRunORM)
            .where(RequirementEvalRunORM.baseline_run_id == baseline_id)
        )
        assert current is not None
    engine.dispose()


def test_requirement_eval_cli_rejects_missing_baseline_without_trace(
    tmp_path: Path,
) -> None:
    database_url, env = _environment(
        tmp_path,
        "requirement-eval-missing-baseline.db",
        "fixture",
    )
    _migrate(env)

    result = _run(env, "--baseline-run-id", "reqeval_missing")

    assert result.returncode == 1
    assert "Baseline Requirement Eval Run 'reqeval_missing' was not found" in result.stdout
    engine = create_engine(database_url)
    with Session(engine) as session:
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 0
        assert int(
            session.scalar(select(func.count()).select_from(RequirementEvalRunORM))
            or 0
        ) == 0
    engine.dispose()


def test_requirement_eval_cli_rejects_disabled_provider_without_trace(
    tmp_path: Path,
) -> None:
    database_url, env = _environment(
        tmp_path,
        "requirement-eval-disabled.db",
        "disabled",
    )
    _migrate(env)

    result = _run(env)

    assert result.returncode == 1
    assert "requires REQUIREMENT_EXTRACTOR_PROVIDER=fixture or openai" in result.stdout
    engine = create_engine(database_url)
    with Session(engine) as session:
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 0
        assert int(
            session.scalar(select(func.count()).select_from(RequirementEvalRunORM))
            or 0
        ) == 0
    engine.dispose()
