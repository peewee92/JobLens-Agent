"""Process-level verification for the Job Requirement Eval CLI."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import TraceSpanORM

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_fixture_requirement_eval_cli_writes_one_trace_per_case(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'requirement-eval-cli.db'}"
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "REQUIREMENT_EXTRACTOR_PROVIDER": "fixture",
    }
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert migration.returncode == 0, migration.stdout + migration.stderr

    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_requirement_eval"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed=10/10" in result.stdout
    assert "capabilityRecall=100.00%" in result.stdout
    assert "importanceAccuracy=100.00%" in result.stdout
    assert "gatePassed=True" in result.stdout
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
    engine.dispose()


def test_requirement_eval_cli_rejects_disabled_provider_without_trace(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'requirement-eval-disabled.db'}"
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "REQUIREMENT_EXTRACTOR_PROVIDER": "disabled",
    }
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert migration.returncode == 0, migration.stdout + migration.stderr

    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_requirement_eval"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "requires REQUIREMENT_EXTRACTOR_PROVIDER=fixture or openai" in result.stdout
    engine = create_engine(database_url)
    with Session(engine) as session:
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 0
    engine.dispose()
