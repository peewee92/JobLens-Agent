"""Application use cases for persisted Requirement Eval runs and Reviews."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.application.ports.requirement_eval_repository import (
    AbstractRequirementEvalQueryRepository,
)
from app.application.ports.requirement_eval_review_unit_of_work import (
    AbstractRequirementEvalReviewUnitOfWork,
)
from app.application.requirement_evals.errors import (
    AcceptedRequirementEvalBaselineNotFoundError,
    InvalidRequirementEvalReviewError,
    RequirementEvalRunAlreadyReviewedError,
    RequirementEvalRunNotFoundError,
)
from app.application.requirement_evals.models import (
    AcceptedRequirementEvalBaseline,
    RequirementEvalReviewDecision,
    RequirementEvalReviewDetail,
    RequirementEvalReviewWrite,
    RequirementEvalRunDetail,
    RequirementEvalRunPage,
)

RequirementEvalReviewUnitOfWorkFactory = Callable[
    [], AbstractRequirementEvalReviewUnitOfWork
]


class ListRequirementEvalRunsUseCase:
    def __init__(self, repository: AbstractRequirementEvalQueryRepository) -> None:
        self._repository = repository

    def execute(self, *, limit: int, offset: int) -> RequirementEvalRunPage:
        return self._repository.list_runs(limit=limit, offset=offset)


class GetRequirementEvalRunUseCase:
    def __init__(self, repository: AbstractRequirementEvalQueryRepository) -> None:
        self._repository = repository

    def execute(self, eval_run_id: str) -> RequirementEvalRunDetail:
        result = self._repository.get_run(eval_run_id)
        if result is None:
            raise RequirementEvalRunNotFoundError(
                f"Requirement Eval Run {eval_run_id!r} was not found"
            )
        return result


class ReviewRequirementEvalRunUseCase:
    """Record one immutable human Review for a live Requirement Eval Run."""

    def __init__(
        self,
        repository: AbstractRequirementEvalQueryRepository,
        uow_factory: RequirementEvalReviewUnitOfWorkFactory,
    ) -> None:
        self._repository = repository
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        eval_run_id: str,
        decision: RequirementEvalReviewDecision,
        reviewer: str,
        notes: str,
    ) -> RequirementEvalReviewDetail:
        run = self._repository.get_summary(eval_run_id)
        if run is None:
            raise RequirementEvalRunNotFoundError(
                f"Requirement Eval Run {eval_run_id!r} was not found"
            )
        if self._repository.get_review(eval_run_id) is not None:
            raise RequirementEvalRunAlreadyReviewedError(
                f"Requirement Eval Run {eval_run_id!r} already has an immutable review"
            )

        normalized_reviewer = reviewer.strip()
        normalized_notes = notes.strip()
        if not normalized_reviewer:
            raise InvalidRequirementEvalReviewError("reviewer must not be blank")
        if len(normalized_notes) < 10:
            raise InvalidRequirementEvalReviewError(
                "notes must contain at least 10 characters after trimming"
            )
        if run.mode != "live":
            raise InvalidRequirementEvalReviewError(
                "Only live Requirement Eval Runs may receive an official review"
            )
        if decision is RequirementEvalReviewDecision.ACCEPTED and not (
            run.gate_passed and run.release_eligible
        ):
            raise InvalidRequirementEvalReviewError(
                "Accepted review requires a Gate-passed, release-eligible live Requirement Eval Run"
            )

        reviewed_at = datetime.now(timezone.utc)
        detail = RequirementEvalReviewDetail(
            id=f"reqreview_{uuid4().hex}",
            eval_run_id=eval_run_id,
            decision=decision,
            reviewer=normalized_reviewer,
            notes=normalized_notes,
            reviewed_at=reviewed_at,
        )
        with self._uow_factory() as uow:
            uow.reviews.add(
                RequirementEvalReviewWrite(
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


class GetAcceptedRequirementEvalBaselineUseCase:
    def __init__(self, repository: AbstractRequirementEvalQueryRepository) -> None:
        self._repository = repository

    def execute(self) -> AcceptedRequirementEvalBaseline:
        result = self._repository.get_accepted_baseline()
        if result is None:
            raise AcceptedRequirementEvalBaselineNotFoundError(
                "No human-accepted live Requirement Eval baseline exists"
            )
        return result
