"""Human review governance tests for Profile Eval runs."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.ports.profile_extractor import AbstractProfileExtractor
from app.application.profile_evals import (
    InvalidProfileEvalReviewError,
    ProfileEvalReviewDecision,
    ProfileEvalRunAlreadyReviewedError,
)
from app.application.profile_evals.use_cases import (
    GetAcceptedProfileEvalBaselineUseCase,
    ReviewProfileEvalRunUseCase,
)
from app.application.profile_extraction import ProfileExtractorResult
from app.db.base import Base
from app.db.models import ProfileEvalReviewORM
from app.evals import ProfileEvalMode, RunProfileEvalUseCase, load_profile_eval_cases
from app.llm import FixtureProfileExtractor
from app.repositories import (
    SqlAlchemyProfileEvalQueryRepository,
    SqlAlchemyProfileEvalReviewUnitOfWork,
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
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'profile-eval-reviews.db'}")

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


def _run_eval(
    factory: sessionmaker[Session],
    *,
    mode: ProfileEvalMode,
    provider: str,
    extractor: AbstractProfileExtractor | None = None,
):
    extractor = extractor or FixtureProfileExtractor()
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
    ).execute(load_profile_eval_cases(DATASET))


def _review_use_case(factory: sessionmaker[Session]) -> ReviewProfileEvalRunUseCase:
    repository = SqlAlchemyProfileEvalQueryRepository(factory)
    return ReviewProfileEvalRunUseCase(
        repository,
        lambda: SqlAlchemyProfileEvalReviewUnitOfWork(factory),
    )


def test_fixture_run_cannot_receive_official_review(
    session_factory: sessionmaker[Session],
) -> None:
    run = _run_eval(
        session_factory,
        mode=ProfileEvalMode.FIXTURE,
        provider="fixture",
    )

    with pytest.raises(InvalidProfileEvalReviewError, match="Only live"):
        _review_use_case(session_factory).execute(
            eval_run_id=run.summary.id,
            decision=ProfileEvalReviewDecision.ACCEPTED,
            reviewer="reviewer",
            notes="Reviewed all cases and Trace evidence.",
        )

    with session_factory() as session:
        assert int(
            session.scalar(select(func.count()).select_from(ProfileEvalReviewORM)) or 0
        ) == 0


def test_gate_failed_live_run_can_be_rejected_but_not_accepted(
    session_factory: sessionmaker[Session],
) -> None:
    failed_run = _run_eval(
        session_factory,
        mode=ProfileEvalMode.LIVE,
        provider="simulated-live",
        extractor=MissingSkillsExtractor(),
    )
    use_case = _review_use_case(session_factory)

    with pytest.raises(InvalidProfileEvalReviewError, match="Gate-passed"):
        use_case.execute(
            eval_run_id=failed_run.summary.id,
            decision=ProfileEvalReviewDecision.ACCEPTED,
            reviewer="reviewer",
            notes="This should not be accepted because the Gate failed.",
        )

    rejected = use_case.execute(
        eval_run_id=failed_run.summary.id,
        decision=ProfileEvalReviewDecision.REJECTED,
        reviewer="reviewer",
        notes="Rejected after reviewing missing-skill failures and Trace evidence.",
    )

    assert rejected.decision is ProfileEvalReviewDecision.REJECTED
    assert SqlAlchemyProfileEvalQueryRepository(
        session_factory
    ).get_accepted_baseline() is None


def test_release_eligible_live_run_can_be_accepted_and_returned_as_baseline(
    session_factory: sessionmaker[Session],
) -> None:
    run = _run_eval(
        session_factory,
        mode=ProfileEvalMode.LIVE,
        provider="simulated-live",
    )
    review = _review_use_case(session_factory).execute(
        eval_run_id=run.summary.id,
        decision=ProfileEvalReviewDecision.ACCEPTED,
        reviewer="local-reviewer",
        notes="Reviewed all ten cases and their Trace evidence without unsupported facts.",
    )

    baseline = GetAcceptedProfileEvalBaselineUseCase(
        SqlAlchemyProfileEvalQueryRepository(session_factory)
    ).execute()

    assert review.id.startswith("review_")
    assert baseline.review.id == review.id
    assert baseline.run.id == run.summary.id
    assert baseline.run.mode == "live"
    assert baseline.run.release_eligible is True

    detail = SqlAlchemyProfileEvalQueryRepository(session_factory).get_run(run.summary.id)
    assert detail is not None
    assert detail.review == review


def test_review_is_immutable_and_duplicate_returns_conflict(
    session_factory: sessionmaker[Session],
) -> None:
    run = _run_eval(
        session_factory,
        mode=ProfileEvalMode.LIVE,
        provider="simulated-live",
    )
    use_case = _review_use_case(session_factory)
    use_case.execute(
        eval_run_id=run.summary.id,
        decision=ProfileEvalReviewDecision.ACCEPTED,
        reviewer="reviewer-a",
        notes="Accepted after reviewing all cases and their Trace evidence.",
    )

    with pytest.raises(ProfileEvalRunAlreadyReviewedError):
        use_case.execute(
            eval_run_id=run.summary.id,
            decision=ProfileEvalReviewDecision.REJECTED,
            reviewer="reviewer-b",
            notes="Attempted overwrite must not replace the immutable first decision.",
        )

    with session_factory() as session:
        reviews = session.scalars(select(ProfileEvalReviewORM)).all()
        assert len(reviews) == 1
        assert reviews[0].decision == "accepted"
        assert reviews[0].reviewer == "reviewer-a"


def test_latest_accepted_review_switches_current_baseline_without_overwriting_history(
    session_factory: sessionmaker[Session],
) -> None:
    first_run = _run_eval(
        session_factory,
        mode=ProfileEvalMode.LIVE,
        provider="simulated-live-a",
    )
    second_run = _run_eval(
        session_factory,
        mode=ProfileEvalMode.LIVE,
        provider="simulated-live-b",
    )
    use_case = _review_use_case(session_factory)
    first_review = use_case.execute(
        eval_run_id=first_run.summary.id,
        decision=ProfileEvalReviewDecision.ACCEPTED,
        reviewer="reviewer",
        notes="Accepted first live baseline after reviewing every case and Trace.",
    )
    second_review = use_case.execute(
        eval_run_id=second_run.summary.id,
        decision=ProfileEvalReviewDecision.ACCEPTED,
        reviewer="reviewer",
        notes="Accepted replacement baseline after comparing all cases and Trace evidence.",
    )

    baseline = SqlAlchemyProfileEvalQueryRepository(
        session_factory
    ).get_accepted_baseline()
    assert baseline is not None
    assert baseline.review.id == second_review.id
    assert baseline.run.id == second_run.summary.id

    with session_factory() as session:
        reviews = session.scalars(
            select(ProfileEvalReviewORM).order_by(ProfileEvalReviewORM.reviewed_at.asc())
        ).all()
        assert [item.id for item in reviews] == [first_review.id, second_review.id]


def test_review_requires_non_blank_reviewer_and_meaningful_notes(
    session_factory: sessionmaker[Session],
) -> None:
    run = _run_eval(
        session_factory,
        mode=ProfileEvalMode.LIVE,
        provider="simulated-live",
    )
    use_case = _review_use_case(session_factory)

    with pytest.raises(InvalidProfileEvalReviewError, match="reviewer"):
        use_case.execute(
            eval_run_id=run.summary.id,
            decision=ProfileEvalReviewDecision.ACCEPTED,
            reviewer="   ",
            notes="Reviewed all evidence and cases.",
        )
    with pytest.raises(InvalidProfileEvalReviewError, match="notes"):
        use_case.execute(
            eval_run_id=run.summary.id,
            decision=ProfileEvalReviewDecision.ACCEPTED,
            reviewer="reviewer",
            notes="too short",
        )
