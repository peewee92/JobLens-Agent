"""Evaluation tests for Job Requirement Extraction."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_requirements import (
    JobRequirementExtractionOutput,
    JobRequirementExtractorResult,
)
from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
from app.db.base import Base
from app.db.models import TraceSpanORM
from app.evals import load_job_requirement_eval_cases, run_job_requirement_eval
from app.llm import FixtureJobRequirementExtractor
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows import ExtractJobRequirementsWorkflow

DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "requirement-extraction"
    / "requirement-extraction-v2.jsonl"
)


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'requirements-eval.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


class DegradedRequirementExtractor(AbstractJobRequirementExtractor):
    def __init__(self) -> None:
        self._fixture = FixtureJobRequirementExtractor()

    @property
    def model_name(self) -> str:
        return "degraded-requirement-extractor"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        result = self._fixture.extract(description)
        requirements = result.output.requirements
        return JobRequirementExtractorResult(
            output=JobRequirementExtractionOutput(
                requirements=requirements[:1]
            ),
            model=self.model_name,
        )


def _workflow(
    factory: sessionmaker[Session],
    extractor: AbstractJobRequirementExtractor,
) -> ExtractJobRequirementsWorkflow:
    return ExtractJobRequirementsWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(factory),
    )


def test_fixture_requirement_eval_passes_pipeline_gate_with_one_trace_per_case(
    session_factory: sessionmaker[Session],
) -> None:
    cases = load_job_requirement_eval_cases(DATASET)

    report = run_job_requirement_eval(
        workflow=_workflow(session_factory, FixtureJobRequirementExtractor()),
        cases=cases,
        dataset_version="requirement-extraction-v2",
    )

    assert len(cases) == 10
    assert report.passed_cases == 10
    assert report.case_pass_rate == 1.0
    assert report.workflow_success_rate == 1.0
    assert report.capability_recall == 1.0
    assert report.importance_accuracy == 1.0
    assert report.forbidden_capability_rate == 0.0
    assert report.gate_passed is True
    assert all(item.trace_run_id for item in report.cases)
    with session_factory() as session:
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 10


def test_degraded_requirement_extractor_fails_gate_with_explainable_cases(
    session_factory: sessionmaker[Session],
) -> None:
    report = run_job_requirement_eval(
        workflow=_workflow(session_factory, DegradedRequirementExtractor()),
        cases=load_job_requirement_eval_cases(DATASET),
        dataset_version="requirement-extraction-v2",
    )

    assert report.gate_passed is False
    assert report.capability_recall < 0.95
    failed = [item for item in report.cases if not item.passed]
    assert failed
    assert any(item.missing_requirements for item in failed)
    assert all(item.trace_run_id for item in report.cases)
