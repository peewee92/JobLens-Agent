"""Synthetic contract eval for the first Semantic Match LLM pipeline."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.evals.semantic_match import load_semantic_match_eval_cases, run_semantic_match_eval
from app.llm.semantic_matchers import FixtureSemanticMatcher
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows.semantic_match import SemanticMatchWorkflow

DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "semantic-match"
    / "semantic-match-v1.jsonl"
)


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'semantic-match-eval.db'}")
    from app.db.base import Base

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_fixture_semantic_match_eval_covers_partial_non_override_contract(
    session_factory: sessionmaker[Session],
) -> None:
    cases = load_semantic_match_eval_cases(DATASET)
    report = run_semantic_match_eval(
        cases=cases,
        workflow=SemanticMatchWorkflow(
            matcher=FixtureSemanticMatcher(),
            trace_uow_factory=lambda: SqlAlchemyTraceUnitOfWork(session_factory),
        ),
    )

    assert report.total == 3
    assert report.passed == 3
    assert report.failed == 0
    assert all(item.passed for item in report.cases)
    mcp = next(item for item in report.cases if item.case_id == "mcp-related-blocked")
    assert mcp.expected_eligibility == "blocked"
    assert mcp.actual_eligibility == "blocked"
    assert mcp.expected_verdict == "partial"
    assert mcp.actual_verdict == "partial"
