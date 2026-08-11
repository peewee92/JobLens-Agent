"""Explicit creation of a transient TargetCohort from current UserFeedback candidates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.application.user_feedback_target_cohort import UserFeedbackTargetCohortSourceResult
from app.domain.target_cohort import (
    TargetCohortFeedbackSource,
    TargetCohortSelectionSource,
    TargetCohortSnapshot,
)


class TargetCohortSelectionError(ValueError):
    """Raised when an explicit cohort selection cannot be proven current."""


@dataclass(frozen=True, slots=True)
class CreateFeedbackTargetCohortCommand:
    cohort_id: str
    name: str
    selected_feedback_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CreateManualTargetCohortCommand:
    cohort_id: str
    name: str
    selected_job_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CreateFeedbackTargetCohortResult:
    cohort: TargetCohortSnapshot
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class FeedbackTargetCohortSource(Protocol):
    def execute(self) -> UserFeedbackTargetCohortSourceResult: ...


class CreateManualTargetCohortUseCase:
    """Create a transient cohort from Jobs explicitly selected on the planning screen."""

    def __init__(self, *, jobs: AbstractJobQueryRepository) -> None:
        self._jobs = jobs

    def execute(
        self,
        command: CreateManualTargetCohortCommand,
    ) -> CreateFeedbackTargetCohortResult:
        selected_job_ids = _stable_unique_ids(command.selected_job_ids)
        if not selected_job_ids:
            raise TargetCohortSelectionError("at least one Job must be selected")

        for job_id in selected_job_ids:
            if self._jobs.get_job(job_id) is None:
                raise TargetCohortSelectionError(
                    f"job {job_id!r} is not available for manual cohort selection"
                )

        cohort = TargetCohortSnapshot.create(
            cohort_id=command.cohort_id,
            name=command.name,
            selection_source=TargetCohortSelectionSource.MANUAL,
            job_ids=selected_job_ids,
        )
        return CreateFeedbackTargetCohortResult(cohort=cohort)


class CreateFeedbackTargetCohortUseCase:
    """Create a cohort only from feedback records explicitly selected by the user.

    The source use case is responsible for exposing only the latest non-rejected feedback
    candidate per Job. This use case never auto-selects candidates and never falls back to
    matching by Job ID when a feedback selection is stale.
    """

    def __init__(self, *, source: FeedbackTargetCohortSource) -> None:
        self._source = source

    def execute(
        self,
        command: CreateFeedbackTargetCohortCommand,
    ) -> CreateFeedbackTargetCohortResult:
        selected_feedback_ids = _stable_unique_feedback_ids(command.selected_feedback_ids)
        if not selected_feedback_ids:
            raise TargetCohortSelectionError("at least one feedback candidate must be selected")

        source_result = self._source.execute()
        candidates_by_feedback_id = {
            candidate.feedback_id: candidate for candidate in source_result.candidates
        }

        selected_candidates = []
        for feedback_id in selected_feedback_ids:
            candidate = candidates_by_feedback_id.get(feedback_id)
            if candidate is None:
                raise TargetCohortSelectionError(
                    f"feedback {feedback_id!r} is not a current cohort candidate"
                )
            selected_candidates.append(candidate)

        cohort = TargetCohortSnapshot.create(
            cohort_id=command.cohort_id,
            name=command.name,
            selection_source=TargetCohortSelectionSource.USER_FEEDBACK,
            job_ids=tuple(candidate.job_id for candidate in selected_candidates),
            created_from_feedback=tuple(
                TargetCohortFeedbackSource(
                    feedback_id=candidate.feedback_id,
                    match_report_id=candidate.match_report_id,
                    job_id=candidate.job_id,
                )
                for candidate in selected_candidates
            ),
        )
        return CreateFeedbackTargetCohortResult(cohort=cohort)


class CreateTargetCohortUseCase:
    """Dispatch explicit cohort creation without inferring the user's selection source."""

    def __init__(
        self,
        *,
        feedback: CreateFeedbackTargetCohortUseCase,
        manual: CreateManualTargetCohortUseCase,
    ) -> None:
        self._feedback = feedback
        self._manual = manual

    def execute(
        self,
        command: CreateFeedbackTargetCohortCommand | CreateManualTargetCohortCommand,
    ) -> CreateFeedbackTargetCohortResult:
        if isinstance(command, CreateManualTargetCohortCommand):
            return self._manual.execute(command)
        return self._feedback.execute(command)


def _stable_unique_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = raw_value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return tuple(normalized)


def _stable_unique_feedback_ids(feedback_ids: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for feedback_id in feedback_ids:
        value = feedback_id.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return tuple(normalized)


__all__ = [
    "CreateFeedbackTargetCohortCommand",
    "CreateFeedbackTargetCohortResult",
    "CreateFeedbackTargetCohortUseCase",
    "CreateManualTargetCohortCommand",
    "CreateManualTargetCohortUseCase",
    "CreateTargetCohortUseCase",
    "TargetCohortSelectionError",
]
