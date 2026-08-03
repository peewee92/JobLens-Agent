"""Application use cases for Profile Eval runs and human review governance."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.application.ports.profile_eval_repository import AbstractProfileEvalQueryRepository
from app.application.ports.profile_eval_review_unit_of_work import (
    AbstractProfileEvalReviewUnitOfWork,
)
from app.application.profile_evals.errors import (
    AcceptedProfileEvalBaselineNotFoundError,
    InvalidProfileEvalReviewError,
    ProfileEvalRunAlreadyReviewedError,
    ProfileEvalRunNotFoundError,
)
from app.application.profile_evals.models import (
    AcceptedProfileEvalBaseline,
    ProfileEvalReviewDecision,
    ProfileEvalReviewDetail,
    ProfileEvalReviewWrite,
    ProfileEvalRunDetail,
    ProfileEvalRunPage,
)

ProfileEvalReviewUnitOfWorkFactory = Callable[[], AbstractProfileEvalReviewUnitOfWork]


class ListProfileEvalRunsUseCase:
    def __init__(self, repository: AbstractProfileEvalQueryRepository) -> None:
        self._repository = repository

    def execute(self, *, limit: int, offset: int) -> ProfileEvalRunPage:
        return self._repository.list_runs(limit=limit, offset=offset)


class GetProfileEvalRunUseCase:
    def __init__(self, repository: AbstractProfileEvalQueryRepository) -> None:
        self._repository = repository

    def execute(self, eval_run_id: str) -> ProfileEvalRunDetail:
        result = self._repository.get_run(eval_run_id)
        if result is None:
            raise ProfileEvalRunNotFoundError(
                f"Profile Eval Run {eval_run_id!r} was not found"
            )
        return result


class ReviewProfileEvalRunUseCase:
    """Record one immutable human review for a live Eval Run."""

    def __init__(
        self,
        repository: AbstractProfileEvalQueryRepository,
        uow_factory: ProfileEvalReviewUnitOfWorkFactory,
    ) -> None:
        self._repository = repository
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        eval_run_id: str,
        decision: ProfileEvalReviewDecision,
        reviewer: str,
        notes: str,
    ) -> ProfileEvalReviewDetail:
        run = self._repository.get_summary(eval_run_id)
        if run is None:
            raise ProfileEvalRunNotFoundError(
                f"Profile Eval Run {eval_run_id!r} was not found"
            )
        if self._repository.get_review(eval_run_id) is not None:
            raise ProfileEvalRunAlreadyReviewedError(
                f"Profile Eval Run {eval_run_id!r} already has an immutable review"
            )

        normalized_reviewer = reviewer.strip()
        normalized_notes = notes.strip()
        if not normalized_reviewer:
            raise InvalidProfileEvalReviewError("reviewer must not be blank")
        if len(normalized_notes) < 10:
            raise InvalidProfileEvalReviewError(
                "notes must contain at least 10 characters after trimming"
            )
        if run.mode != "live":
            raise InvalidProfileEvalReviewError(
                "Only live Profile Eval Runs may receive an official review"
            )
        if decision is ProfileEvalReviewDecision.ACCEPTED and not (
            run.gate_passed and run.release_eligible
        ):
            raise InvalidProfileEvalReviewError(
                "Accepted review requires a Gate-passed, release-eligible live Eval Run"
            )

        reviewed_at = datetime.now(timezone.utc)
        detail = ProfileEvalReviewDetail(
            id=f"review_{uuid4().hex}",
            eval_run_id=eval_run_id,
            decision=decision,
            reviewer=normalized_reviewer,
            notes=normalized_notes,
            reviewed_at=reviewed_at,
        )
        with self._uow_factory() as uow:
            uow.reviews.add(
                ProfileEvalReviewWrite(
                    review_id=detail.id,
                    eval_run_id=detail.eval_run_id,
                    decision=detail.decision,
                    reviewer=detail.reviewer,
                    notes=detail.notes,
                    reviewed_at=detail.reviewed_at,
                )
            )
            uow.commit()
        return detail


class GetAcceptedProfileEvalBaselineUseCase:
    def __init__(self, repository: AbstractProfileEvalQueryRepository) -> None:
        self._repository = repository

    def execute(self) -> AcceptedProfileEvalBaseline:
        result = self._repository.get_accepted_baseline()
        if result is None:
            raise AcceptedProfileEvalBaselineNotFoundError(
                "No human-accepted live Profile Eval baseline exists"
            )
        return result
