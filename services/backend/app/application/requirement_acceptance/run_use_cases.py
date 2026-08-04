"""Read and human Canary-review use cases for Requirement acceptance runs."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.application.ports.requirement_acceptance_run_repository import (
    AbstractRequirementAcceptanceRunQueryRepository,
)
from app.application.ports.requirement_acceptance_run_unit_of_work import (
    AbstractRequirementAcceptanceRunUnitOfWork,
)
from app.application.requirement_acceptance.errors import (
    InvalidRequirementAcceptanceCanaryReviewError,
    RequirementAcceptanceCanaryReviewAlreadyExistsError,
    RequirementAcceptanceRunNotFoundError,
)
from app.application.requirement_acceptance.runs import (
    RequirementAcceptanceCanaryDecision,
    RequirementAcceptanceCanaryReviewDetail,
    RequirementAcceptanceCanaryReviewWrite,
    RequirementAcceptanceRunDetail,
    RequirementAcceptanceRunPage,
)

RequirementAcceptanceRunUnitOfWorkFactory = Callable[
    [], AbstractRequirementAcceptanceRunUnitOfWork
]
MIN_CANARY_REVIEW_NOTES = 20


class ListRequirementAcceptanceRunsUseCase:
    def __init__(
        self,
        repository: AbstractRequirementAcceptanceRunQueryRepository,
    ) -> None:
        self._repository = repository

    def execute(self, *, limit: int, offset: int) -> RequirementAcceptanceRunPage:
        return self._repository.list_runs(limit=limit, offset=offset)


class GetRequirementAcceptanceRunUseCase:
    def __init__(
        self,
        repository: AbstractRequirementAcceptanceRunQueryRepository,
    ) -> None:
        self._repository = repository

    def execute(self, run_id: str) -> RequirementAcceptanceRunDetail:
        result = self._repository.get_run(run_id)
        if result is None:
            raise RequirementAcceptanceRunNotFoundError(
                f"Requirement acceptance run {run_id!r} was not found"
            )
        return result


class ReviewRequirementAcceptanceCanaryUseCase:
    """Freeze one human go/stop decision over the first 1–3 attempted cases."""

    def __init__(
        self,
        repository: AbstractRequirementAcceptanceRunQueryRepository,
        uow_factory: RequirementAcceptanceRunUnitOfWorkFactory,
    ) -> None:
        self._repository = repository
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        run_id: str,
        reviewer: str,
        decision: RequirementAcceptanceCanaryDecision,
        notes: str,
    ) -> RequirementAcceptanceCanaryReviewDetail:
        run = self._repository.get_run(run_id)
        if run is None:
            raise RequirementAcceptanceRunNotFoundError(
                f"Requirement acceptance run {run_id!r} was not found"
            )
        if run.canary_review is not None:
            raise RequirementAcceptanceCanaryReviewAlreadyExistsError(
                f"Requirement acceptance run {run_id!r} already has an immutable Canary review"
            )
        normalized_reviewer = reviewer.strip()
        normalized_notes = notes.strip()
        if normalized_reviewer != run.reviewer:
            raise InvalidRequirementAcceptanceCanaryReviewError(
                "Canary reviewer must match the reviewer who owns the Requirement acceptance run"
            )
        if len(normalized_notes) < MIN_CANARY_REVIEW_NOTES:
            raise InvalidRequirementAcceptanceCanaryReviewError(
                f"Canary review notes must contain at least {MIN_CANARY_REVIEW_NOTES} characters"
            )

        attempted_cases = tuple(
            case for case in run.cases if case.was_attempted
        )
        allowed = (
            run.canary_continue_allowed
            if decision is RequirementAcceptanceCanaryDecision.CONTINUE
            else run.canary_stop_allowed
        )
        if not allowed:
            raise InvalidRequirementAcceptanceCanaryReviewError(
                run.canary_review_block_reason
                or "The requested Canary decision is not allowed for this Run state"
            )

        reviewed_at = datetime.now(timezone.utc)
        write = RequirementAcceptanceCanaryReviewWrite(
            review_id=f"reqacceptcanary_{uuid4().hex}",
            run_id=run.id,
            reviewer=normalized_reviewer,
            decision=decision,
            notes=normalized_notes,
            reviewed_case_ids=tuple(case.id for case in attempted_cases),
            reviewed_extraction_ids=tuple(
                case.extraction_id
                for case in attempted_cases
                if case.extraction_id is not None
            ),
            reviewed_trace_run_ids=tuple(
                case.trace_run_id
                for case in attempted_cases
                if case.trace_run_id is not None
            ),
            reviewed_at=reviewed_at,
        )
        with self._uow_factory() as uow:
            uow.runs.add_canary_review(write)
            uow.commit()

        result = self._repository.get_canary_review(run.id)
        if result is None:  # pragma: no cover - defensive persistence invariant
            raise RuntimeError(
                f"Persisted Canary review for Requirement acceptance run {run.id!r} cannot be read"
            )
        return result
