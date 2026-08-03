"""Persistence, quality gate and comparison tests for Requirement Eval runs."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_requirements import (
    JobRequirementExtractionOutput,
    JobRequirementExtractorResult,
    RequirementExtractorFailedError,
)
from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
from app.application.requirement_evals import RequirementEvalRunNotFoundError
from app.db.base import Base
from app.db.models import (
    RequirementEvalCaseResultORM,
    RequirementEvalRunORM,
    TraceSpanORM,
)
from app.evals import (
    RequirementEvalMode,
    RunRequirementEvalUseCase,
    load_job_requirement_eval_cases,
)
from app.llm import FixtureJobRequirementExtractor
from app.repositories import (
    SqlAlchemyRequirementEvalQueryRepository,
    SqlAlchemyRequirementEvalUnitOfWork,
    SqlAlchemyTraceUnitOfWork,
)
from app.workflows import ExtractJobRequirementsWorkflow

DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "requirement-extraction"
    / "requirement-extraction-v1.jsonl"
)


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'requirement-eval-runs.db'}")

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


class DegradedRequirementExtractor(AbstractJobRequirementExtractor):
    def __init__(self) -> None:
        self._fixture = FixtureJobRequirementExtractor()

    @property
    def model_name(self) -> str:
        return "degraded-requirement-extractor"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        result = self._fixture.extract(description)
        return JobRequirementExtractorResult(
            output=JobRequirementExtractionOutput(
                requirements=result.output.requirements[:1]
            ),
            model=self.model_name,
        )


class FailingRequirementExtractor(AbstractJobRequirementExtractor):
    @property
    def model_name(self) -> str:
        return "failing-requirement-extractor"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        raise RequirementExtractorFailedError("simulated provider failure")


class PersistenceFailingRequirementEvalUnitOfWork:
    """Test double proving Trace evidence is outside final Eval persistence."""

    eval_runs: "PersistenceFailingRequirementEvalUnitOfWork"

    def __enter__(self) -> "PersistenceFailingRequirementEvalUnitOfWork":
        self.eval_runs = self
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def add(self, _run) -> None:
        raise RuntimeError("simulated Requirement Eval persistence failure")

    def commit(self) -> None:  # pragma: no cover - add always fails first
        raise AssertionError("commit must not run after add failure")


def _run_use_case(
    factory: sessionmaker[Session],
    *,
    extractor: AbstractJobRequirementExtractor,
    mode: RequirementEvalMode,
    provider: str,
    baseline_run_id: str | None = None,
):
    workflow = ExtractJobRequirementsWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(factory),
    )
    repository = SqlAlchemyRequirementEvalQueryRepository(factory)
    return RunRequirementEvalUseCase(
        workflow=workflow,
        eval_uow_factory=lambda: SqlAlchemyRequirementEvalUnitOfWork(factory),
        query_repository=repository,
        dataset_version="requirement-extraction-v1",
        mode=mode,
        provider=provider,
        model=extractor.model_name,
    ).execute(
        load_job_requirement_eval_cases(DATASET),
        baseline_run_id=baseline_run_id,
    )


def test_fixture_run_persists_cases_and_traces_without_release_eligibility(
    session_factory: sessionmaker[Session],
) -> None:
    detail = _run_use_case(
        session_factory,
        extractor=FixtureJobRequirementExtractor(),
        mode=RequirementEvalMode.FIXTURE,
        provider="fixture",
    )

    assert detail.summary.gate_version == "requirement-eval-gate-v1"
    assert detail.summary.gate_passed is True
    assert detail.summary.release_eligible is False
    assert detail.summary.passed_cases == 10
    assert detail.summary.capability_recall == 1.0
    assert len(detail.cases) == 10
    assert all(item.passed and item.trace_run_id for item in detail.cases)

    with session_factory() as session:
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
        assert int(
            session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0
        ) == 10


def test_provider_failures_keep_case_to_error_trace_links(
    session_factory: sessionmaker[Session],
) -> None:
    detail = _run_use_case(
        session_factory,
        extractor=FailingRequirementExtractor(),
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
    )

    assert detail.summary.gate_passed is False
    assert detail.summary.release_eligible is False
    assert detail.summary.workflow_success_rate == 0.0
    assert all(not item.passed for item in detail.cases)
    assert all(item.error == "simulated provider failure" for item in detail.cases)
    assert all(
        item.trace_run_id and item.trace_run_id.startswith("run_")
        for item in detail.cases
    )


def test_degraded_live_run_fails_gate_and_records_missing_requirements(
    session_factory: sessionmaker[Session],
) -> None:
    detail = _run_use_case(
        session_factory,
        extractor=DegradedRequirementExtractor(),
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
    )

    assert detail.summary.gate_passed is False
    assert detail.summary.release_eligible is False
    assert detail.summary.capability_recall < 0.95
    failed = [item for item in detail.cases if not item.passed]
    assert failed
    assert any(item.missing_requirements for item in failed)
    assert all(item.trace_run_id for item in failed)


def test_only_gate_passed_live_mode_can_be_release_eligible(
    session_factory: sessionmaker[Session],
) -> None:
    detail = _run_use_case(
        session_factory,
        extractor=FixtureJobRequirementExtractor(),
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
    )

    assert detail.summary.gate_passed is True
    assert detail.summary.release_eligible is True


def test_live_mode_rejects_fixture_provider_label(
    session_factory: sessionmaker[Session],
) -> None:
    extractor = FixtureJobRequirementExtractor()
    workflow = ExtractJobRequirementsWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(session_factory),
    )
    repository = SqlAlchemyRequirementEvalQueryRepository(session_factory)

    with pytest.raises(ValueError, match="cannot use the fixture provider"):
        RunRequirementEvalUseCase(
            workflow=workflow,
            eval_uow_factory=lambda: SqlAlchemyRequirementEvalUnitOfWork(
                session_factory
            ),
            query_repository=repository,
            dataset_version="requirement-extraction-v1",
            mode=RequirementEvalMode.LIVE,
            provider="fixture",
            model=extractor.model_name,
        )


def test_eval_persistence_failure_keeps_diagnostic_traces_but_no_eval_rows(
    session_factory: sessionmaker[Session],
) -> None:
    extractor = FixtureJobRequirementExtractor()
    workflow = ExtractJobRequirementsWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(session_factory),
    )
    repository = SqlAlchemyRequirementEvalQueryRepository(session_factory)

    with pytest.raises(
        RuntimeError,
        match="simulated Requirement Eval persistence failure",
    ):
        RunRequirementEvalUseCase(
            workflow=workflow,
            eval_uow_factory=PersistenceFailingRequirementEvalUnitOfWork,
            query_repository=repository,
            dataset_version="requirement-extraction-v1",
            mode=RequirementEvalMode.FIXTURE,
            provider="fixture",
            model=extractor.model_name,
        ).execute(load_job_requirement_eval_cases(DATASET))

    with session_factory() as session:
        assert int(
            session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0
        ) == 10
        assert int(
            session.scalar(select(func.count()).select_from(RequirementEvalRunORM))
            or 0
        ) == 0
        assert int(
            session.scalar(
                select(func.count()).select_from(RequirementEvalCaseResultORM)
            )
            or 0
        ) == 0


def test_database_rejects_fixture_release_eligibility(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            RequirementEvalRunORM(
                id="reqeval_invalid",
                dataset_version="requirement-extraction-v1",
                mode="fixture",
                provider="fixture",
                model="fixture",
                extractor_version="v1",
                prompt_version="v1",
                gate_version="v1",
                total_cases=1,
                passed_cases=1,
                case_pass_rate=1.0,
                workflow_success_rate=1.0,
                capability_recall=1.0,
                importance_accuracy=1.0,
                forbidden_capability_rate=0.0,
                gate_passed=True,
                release_eligible=True,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_baseline_comparison_reports_negative_quality_deltas(
    session_factory: sessionmaker[Session],
) -> None:
    baseline = _run_use_case(
        session_factory,
        extractor=FixtureJobRequirementExtractor(),
        mode=RequirementEvalMode.FIXTURE,
        provider="fixture",
    )
    current = _run_use_case(
        session_factory,
        extractor=DegradedRequirementExtractor(),
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
        baseline_run_id=baseline.summary.id,
    )

    assert current.comparison is not None
    assert current.comparison.baseline_run_id == baseline.summary.id
    assert current.comparison.capability_recall_delta < 0
    assert current.comparison.case_pass_rate_delta < 0


def test_missing_baseline_is_rejected_before_any_workflow_trace(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(RequirementEvalRunNotFoundError):
        _run_use_case(
            session_factory,
            extractor=FixtureJobRequirementExtractor(),
            mode=RequirementEvalMode.FIXTURE,
            provider="fixture",
            baseline_run_id="reqeval_missing",
        )

    with session_factory() as session:
        assert int(
            session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0
        ) == 0
        assert int(
            session.scalar(select(func.count()).select_from(RequirementEvalRunORM))
            or 0
        ) == 0
