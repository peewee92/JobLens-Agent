"""Human review governance tests for Requirement Eval runs."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_requirements import (
    JobRequirementExtractionOutput,
    JobRequirementExtractorResult,
)
from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
from app.application.ports.requirement_eval_review_repository import (
    AbstractRequirementEvalReviewRepository,
)
from app.application.ports.requirement_eval_review_unit_of_work import (
    AbstractRequirementEvalReviewUnitOfWork,
)
from app.application.requirement_evals import (
    InvalidRequirementEvalReviewError,
    RequirementEvalReviewDecision,
    RequirementEvalRunAlreadyReviewedError,
)
from app.application.requirement_evals.use_cases import (
    GetAcceptedRequirementEvalBaselineUseCase,
    ReviewRequirementEvalRunUseCase,
)
from app.db.base import Base
from app.db.models import RequirementEvalReviewORM
from app.evals import (
    RequirementEvalMode,
    RunRequirementEvalUseCase,
    load_job_requirement_eval_cases,
)
from app.llm import FixtureJobRequirementExtractor
from app.repositories import (
    SqlAlchemyRequirementEvalQueryRepository,
    SqlAlchemyRequirementEvalReviewUnitOfWork,
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
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'requirement-eval-reviews.db'}"
    )

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


def _run_eval(
    factory: sessionmaker[Session],
    *,
    mode: RequirementEvalMode,
    provider: str,
    extractor: AbstractJobRequirementExtractor | None = None,
):
    extractor = extractor or FixtureJobRequirementExtractor()
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
    ).execute(load_job_requirement_eval_cases(DATASET))


def _review_use_case(
    factory: sessionmaker[Session],
) -> ReviewRequirementEvalRunUseCase:
    repository = SqlAlchemyRequirementEvalQueryRepository(factory)
    return ReviewRequirementEvalRunUseCase(
        repository,
        lambda: SqlAlchemyRequirementEvalReviewUnitOfWork(factory),
    )


def test_fixture_run_cannot_receive_official_review(
    session_factory: sessionmaker[Session],
) -> None:
    run = _run_eval(
        session_factory,
        mode=RequirementEvalMode.FIXTURE,
        provider="fixture",
    )

    with pytest.raises(InvalidRequirementEvalReviewError, match="Only live"):
        _review_use_case(session_factory).execute(
            eval_run_id=run.summary.id,
            decision=RequirementEvalReviewDecision.REJECTED,
            reviewer="reviewer",
            notes="Fixture evidence is not eligible for official governance review.",
        )

    with session_factory() as session:
        assert int(
            session.scalar(
                select(func.count()).select_from(RequirementEvalReviewORM)
            )
            or 0
        ) == 0


def test_gate_failed_live_run_can_be_rejected_but_not_accepted(
    session_factory: sessionmaker[Session],
) -> None:
    failed_run = _run_eval(
        session_factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
        extractor=DegradedRequirementExtractor(),
    )
    use_case = _review_use_case(session_factory)

    with pytest.raises(InvalidRequirementEvalReviewError, match="Gate-passed"):
        use_case.execute(
            eval_run_id=failed_run.summary.id,
            decision=RequirementEvalReviewDecision.ACCEPTED,
            reviewer="reviewer",
            notes="This run must not be accepted because capability recall failed.",
        )

    rejected = use_case.execute(
        eval_run_id=failed_run.summary.id,
        decision=RequirementEvalReviewDecision.REJECTED,
        reviewer="reviewer",
        notes="Rejected after checking missing requirements and each linked Trace.",
    )

    assert rejected.decision is RequirementEvalReviewDecision.REJECTED
    assert SqlAlchemyRequirementEvalQueryRepository(
        session_factory
    ).get_accepted_baseline() is None


def test_release_eligible_live_run_can_be_accepted_and_returned_as_baseline(
    session_factory: sessionmaker[Session],
) -> None:
    run = _run_eval(
        session_factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
    )
    review = _review_use_case(session_factory).execute(
        eval_run_id=run.summary.id,
        decision=RequirementEvalReviewDecision.ACCEPTED,
        reviewer="local-reviewer",
        notes="Reviewed all ten Requirement cases and Trace evidence for grounding.",
    )

    baseline = GetAcceptedRequirementEvalBaselineUseCase(
        SqlAlchemyRequirementEvalQueryRepository(session_factory)
    ).execute()

    assert review.id.startswith("reqreview_")
    assert baseline.review.id == review.id
    assert baseline.run.id == run.summary.id
    assert baseline.run.mode == "live"
    assert baseline.run.release_eligible is True

    detail = SqlAlchemyRequirementEvalQueryRepository(session_factory).get_run(
        run.summary.id
    )
    assert detail is not None
    assert detail.review == review


def test_review_is_immutable_and_duplicate_is_rejected(
    session_factory: sessionmaker[Session],
) -> None:
    run = _run_eval(
        session_factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
    )
    use_case = _review_use_case(session_factory)
    use_case.execute(
        eval_run_id=run.summary.id,
        decision=RequirementEvalReviewDecision.ACCEPTED,
        reviewer="reviewer-a",
        notes="Accepted after reviewing every Requirement case and Trace evidence.",
    )

    with pytest.raises(RequirementEvalRunAlreadyReviewedError):
        use_case.execute(
            eval_run_id=run.summary.id,
            decision=RequirementEvalReviewDecision.REJECTED,
            reviewer="reviewer-b",
            notes="Attempted overwrite must not replace the immutable first decision.",
        )

    with session_factory() as session:
        reviews = session.scalars(select(RequirementEvalReviewORM)).all()
        assert len(reviews) == 1
        assert reviews[0].decision == "accepted"
        assert reviews[0].reviewer == "reviewer-a"


def test_database_unique_conflict_is_translated_when_precheck_is_stale(
    session_factory: sessionmaker[Session],
) -> None:
    run = _run_eval(
        session_factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
    )
    _review_use_case(session_factory).execute(
        eval_run_id=run.summary.id,
        decision=RequirementEvalReviewDecision.ACCEPTED,
        reviewer="reviewer-a",
        notes="Accepted after checking all Requirement cases and Trace evidence.",
    )
    real_repository = SqlAlchemyRequirementEvalQueryRepository(session_factory)

    class StaleQueryRepository:
        def get_summary(self, eval_run_id: str):
            return real_repository.get_summary(eval_run_id)

        def get_review(self, eval_run_id: str):
            return None

    stale_use_case = ReviewRequirementEvalRunUseCase(
        StaleQueryRepository(),  # type: ignore[arg-type]
        lambda: SqlAlchemyRequirementEvalReviewUnitOfWork(session_factory),
    )

    with pytest.raises(RequirementEvalRunAlreadyReviewedError):
        stale_use_case.execute(
            eval_run_id=run.summary.id,
            decision=RequirementEvalReviewDecision.REJECTED,
            reviewer="reviewer-b",
            notes="A stale precheck must still be stopped by the database constraint.",
        )

    with session_factory() as session:
        assert int(
            session.scalar(
                select(func.count()).select_from(RequirementEvalReviewORM)
            )
            or 0
        ) == 1


def test_latest_accepted_review_becomes_baseline_without_overwriting_history(
    session_factory: sessionmaker[Session],
) -> None:
    first_run = _run_eval(
        session_factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live-a",
    )
    second_run = _run_eval(
        session_factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live-b",
    )
    use_case = _review_use_case(session_factory)
    first_review = use_case.execute(
        eval_run_id=first_run.summary.id,
        decision=RequirementEvalReviewDecision.ACCEPTED,
        reviewer="reviewer",
        notes="Accepted first Requirement baseline after reviewing every linked Trace.",
    )
    second_review = use_case.execute(
        eval_run_id=second_run.summary.id,
        decision=RequirementEvalReviewDecision.ACCEPTED,
        reviewer="reviewer",
        notes="Accepted replacement baseline after comparing all Requirement evidence.",
    )

    baseline = SqlAlchemyRequirementEvalQueryRepository(
        session_factory
    ).get_accepted_baseline()
    assert baseline is not None
    assert baseline.review.id == second_review.id
    assert baseline.run.id == second_run.summary.id

    with session_factory() as session:
        reviews = session.scalars(
            select(RequirementEvalReviewORM).order_by(
                RequirementEvalReviewORM.reviewed_at.asc()
            )
        ).all()
        assert [item.id for item in reviews] == [first_review.id, second_review.id]


def test_review_requires_non_blank_reviewer_and_meaningful_notes(
    session_factory: sessionmaker[Session],
) -> None:
    run = _run_eval(
        session_factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
    )
    use_case = _review_use_case(session_factory)

    with pytest.raises(InvalidRequirementEvalReviewError, match="reviewer"):
        use_case.execute(
            eval_run_id=run.summary.id,
            decision=RequirementEvalReviewDecision.ACCEPTED,
            reviewer="   ",
            notes="Reviewed all Requirement evidence and Trace records.",
        )
    with pytest.raises(InvalidRequirementEvalReviewError, match="notes"):
        use_case.execute(
            eval_run_id=run.summary.id,
            decision=RequirementEvalReviewDecision.ACCEPTED,
            reviewer="reviewer",
            notes="too short",
        )


class _FailingReviewRepository(AbstractRequirementEvalReviewRepository):
    def add(self, review) -> None:
        raise RuntimeError("simulated review persistence failure")


class _FailingReviewUnitOfWork(AbstractRequirementEvalReviewUnitOfWork):
    reviews = _FailingReviewRepository()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def commit(self) -> None:
        raise AssertionError("commit must not run after add failure")

    def rollback(self) -> None:
        return None


def test_persistence_failure_does_not_create_partial_review(
    session_factory: sessionmaker[Session],
) -> None:
    run = _run_eval(
        session_factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
    )
    use_case = ReviewRequirementEvalRunUseCase(
        SqlAlchemyRequirementEvalQueryRepository(session_factory),
        _FailingReviewUnitOfWork,
    )

    with pytest.raises(RuntimeError, match="persistence failure"):
        use_case.execute(
            eval_run_id=run.summary.id,
            decision=RequirementEvalReviewDecision.ACCEPTED,
            reviewer="reviewer",
            notes="Reviewed all Requirement cases before simulated persistence failure.",
        )

    with session_factory() as session:
        assert int(
            session.scalar(
                select(func.count()).select_from(RequirementEvalReviewORM)
            )
            or 0
        ) == 0
