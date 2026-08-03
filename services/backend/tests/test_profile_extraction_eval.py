"""Repeatable CI gate for the Profile Extraction evaluation dataset."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import TraceSpanORM
from app.evals import load_profile_eval_cases, run_profile_eval
from app.llm import FixtureProfileExtractor
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows import ProposeProfileFromResumeWorkflow

DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "profile-extraction"
    / "profile-extraction-v1.jsonl"
)


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'profile-eval.db'}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_profile_extraction_eval_dataset_has_ten_cases_and_traces_every_run(
    session_factory: sessionmaker[Session],
) -> None:
    cases = load_profile_eval_cases(DATASET)
    workflow = ProposeProfileFromResumeWorkflow(
        FixtureProfileExtractor(),
        lambda: SqlAlchemyTraceUnitOfWork(session_factory),
    )

    report = run_profile_eval(workflow, cases)

    assert len(cases) == 10
    assert report.total == 10
    assert report.passed == 10, report.failures
    assert report.pass_rate == 1.0
    with session_factory() as session:
        trace_count = int(
            session.scalar(
                select(func.count()).select_from(TraceSpanORM)
            )
            or 0
        )
        assert trace_count == 10
