"""Persistence, quality gate and comparison tests for Profile Eval runs."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.ports.profile_extractor import AbstractProfileExtractor
from app.application.profile_extraction import (
    ProfileExtractorFailedError,
    ProfileExtractorResult,
)
from app.db.base import Base
from app.db.models import ProfileEvalCaseResultORM, ProfileEvalRunORM, TraceSpanORM
from app.evals import ProfileEvalMode, RunProfileEvalUseCase, load_profile_eval_cases
from app.llm import FixtureProfileExtractor
from app.repositories import (
    SqlAlchemyProfileEvalQueryRepository,
    SqlAlchemyProfileEvalUnitOfWork,
    SqlAlchemyTraceUnitOfWork,
)
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
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'profile-eval-runs.db'}")

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


class FailingExtractor(AbstractProfileExtractor):
    @property
    def model_name(self) -> str:
        return "failing-profile-extractor"

    def extract(self, resume_text: str) -> ProfileExtractorResult:
        raise ProfileExtractorFailedError("simulated provider failure")


class MissingSkillsExtractor(AbstractProfileExtractor):
    def __init__(self) -> None:
        self._fixture = FixtureProfileExtractor()

    @property
    def model_name(self) -> str:
        return "degraded-profile-extractor"

    def extract(self, resume_text: str) -> ProfileExtractorResult:
        result = self._fixture.extract(resume_text)
        return ProfileExtractorResult(
            output=result.output.__class__(
                headline=result.output.headline,
                years_of_experience=result.output.years_of_experience,
                evidence=result.output.evidence,
                skills=result.output.skills[:1],
                warnings=result.output.warnings,
            ),
            model=self.model_name,
        )


def _run_use_case(
    factory: sessionmaker[Session],
    *,
    extractor: AbstractProfileExtractor,
    mode: ProfileEvalMode,
    provider: str,
    baseline_run_id: str | None = None,
):
    workflow = ProposeProfileFromResumeWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(factory),
    )
    repository = SqlAlchemyProfileEvalQueryRepository(factory)
    return RunProfileEvalUseCase(
        workflow=workflow,
        eval_uow_factory=lambda: SqlAlchemyProfileEvalUnitOfWork(factory),
        query_repository=repository,
        dataset_version="profile-extraction-v1",
        mode=mode,
        provider=provider,
        model=extractor.model_name,
    ).execute(
        load_profile_eval_cases(DATASET),
        baseline_run_id=baseline_run_id,
    )


def test_fixture_run_persists_cases_and_traces_without_release_eligibility(
    session_factory: sessionmaker[Session],
) -> None:
    detail = _run_use_case(
        session_factory,
        extractor=FixtureProfileExtractor(),
        mode=ProfileEvalMode.FIXTURE,
        provider="fixture",
    )

    assert detail.summary.gate_passed is True
    assert detail.summary.release_eligible is False
    assert detail.summary.passed_cases == 10
    assert detail.summary.skill_recall == 1.0
    assert len(detail.cases) == 10
    assert all(item.passed and item.trace_run_id for item in detail.cases)

    with session_factory() as session:
        assert int(session.scalar(select(func.count()).select_from(ProfileEvalRunORM)) or 0) == 1
        assert int(session.scalar(select(func.count()).select_from(ProfileEvalCaseResultORM)) or 0) == 10
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 10


def test_provider_failures_keep_case_to_error_trace_links(
    session_factory: sessionmaker[Session],
) -> None:
    detail = _run_use_case(
        session_factory,
        extractor=FailingExtractor(),
        mode=ProfileEvalMode.LIVE,
        provider="simulated-live",
    )

    assert detail.summary.gate_passed is False
    assert detail.summary.workflow_success_rate == 0.0
    assert all(not item.passed for item in detail.cases)
    assert all("workflow_execution_failed" in item.failure_codes for item in detail.cases)
    assert all(item.trace_run_id and item.trace_run_id.startswith("run_") for item in detail.cases)
    with session_factory() as session:
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 10


def test_degraded_live_run_fails_gate_and_records_case_level_reasons(
    session_factory: sessionmaker[Session],
) -> None:
    detail = _run_use_case(
        session_factory,
        extractor=MissingSkillsExtractor(),
        mode=ProfileEvalMode.LIVE,
        provider="simulated-live",
    )

    assert detail.summary.gate_passed is False
    assert detail.summary.release_eligible is False
    assert detail.summary.skill_recall < 0.95
    failed = [item for item in detail.cases if not item.passed]
    assert failed
    assert all("missing_expected_skill" in item.failure_codes for item in failed)
    assert all(item.trace_run_id for item in failed)


def test_live_mode_rejects_fixture_provider_label(
    session_factory: sessionmaker[Session],
) -> None:
    extractor = FixtureProfileExtractor()
    workflow = ProposeProfileFromResumeWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(session_factory),
    )
    repository = SqlAlchemyProfileEvalQueryRepository(session_factory)
    with pytest.raises(ValueError, match="cannot use the fixture provider"):
        RunProfileEvalUseCase(
            workflow=workflow,
            eval_uow_factory=lambda: SqlAlchemyProfileEvalUnitOfWork(session_factory),
            query_repository=repository,
            dataset_version="profile-extraction-v1",
            mode=ProfileEvalMode.LIVE,
            provider="fixture",
            model=extractor.model_name,
        )


def test_only_live_mode_can_be_release_eligible(
    session_factory: sessionmaker[Session],
) -> None:
    detail = _run_use_case(
        session_factory,
        extractor=FixtureProfileExtractor(),
        mode=ProfileEvalMode.LIVE,
        provider="simulated-live",
    )

    assert detail.summary.gate_passed is True
    assert detail.summary.release_eligible is True


def test_baseline_comparison_reports_negative_skill_recall_delta(
    session_factory: sessionmaker[Session],
) -> None:
    baseline = _run_use_case(
        session_factory,
        extractor=FixtureProfileExtractor(),
        mode=ProfileEvalMode.FIXTURE,
        provider="fixture",
    )
    current = _run_use_case(
        session_factory,
        extractor=MissingSkillsExtractor(),
        mode=ProfileEvalMode.LIVE,
        provider="simulated-live",
        baseline_run_id=baseline.summary.id,
    )

    assert current.comparison is not None
    assert current.comparison.baseline_run_id == baseline.summary.id
    assert current.comparison.skill_recall_delta < 0
    assert current.comparison.case_pass_rate_delta < 0


def test_missing_baseline_is_rejected_before_any_workflow_trace(
    session_factory: sessionmaker[Session],
) -> None:
    from app.application.profile_evals import ProfileEvalRunNotFoundError

    with pytest.raises(ProfileEvalRunNotFoundError):
        _run_use_case(
            session_factory,
            extractor=FixtureProfileExtractor(),
            mode=ProfileEvalMode.FIXTURE,
            provider="fixture",
            baseline_run_id="eval_missing",
        )

    with session_factory() as session:
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 0
        assert int(session.scalar(select(func.count()).select_from(ProfileEvalRunORM)) or 0) == 0
