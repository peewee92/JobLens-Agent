"""Process-level verification for the Profile Eval CLI."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import ProfileEvalCaseResultORM, ProfileEvalRunORM, TraceSpanORM

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_fixture_cli_persists_gate_result_without_live_release_eligibility(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'profile-eval-cli.db'}"
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "PROFILE_EXTRACTOR_PROVIDER": "fixture",
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
        [sys.executable, "-m", "scripts.run_profile_eval"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "gatePassed=True" in result.stdout
    assert "releaseEligible=False" in result.stdout
    match = re.search(r"id=(eval_[a-f0-9]+)", result.stdout)
    assert match is not None

    engine = create_engine(database_url)
    with Session(engine) as session:
        run = session.get(ProfileEvalRunORM, match.group(1))
        assert run is not None
        assert run.mode == "fixture"
        assert run.gate_passed is True
        assert run.release_eligible is False
        assert int(
            session.scalar(select(func.count()).select_from(ProfileEvalCaseResultORM))
            or 0
        ) == 10
        assert int(
            session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0
        ) == 10
    engine.dispose()


def test_cli_rejects_missing_baseline_without_persisting_a_run(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'profile-eval-cli-missing.db'}"
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "PROFILE_EXTRACTOR_PROVIDER": "fixture",
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
        [
            sys.executable,
            "-m",
            "scripts.run_profile_eval",
            "--baseline-run-id",
            "eval_missing",
        ],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Baseline Profile Eval Run" in result.stdout
    engine = create_engine(database_url)
    with Session(engine) as session:
        assert int(
            session.scalar(select(func.count()).select_from(ProfileEvalRunORM)) or 0
        ) == 0
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 0
    engine.dispose()
