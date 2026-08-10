"""Read-only UserFeedback source candidates for a future Target Cohort.

This module does not create a TargetCohort or infer user intent. It exposes the latest
observed decision per Job with immutable feedback and MatchReport provenance so v0.2 can
build an explicit cohort without losing the evidence trail.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.ports.user_feedback_repository import AbstractUserFeedbackQueryRepository
from app.application.user_feedback import UserFeedbackPersistenceNotReadyError
from app.application.user_feedback_persistence import UserFeedbackPersistenceReadiness
from app.domain.user_feedback import FeedbackDecision, StoredUserFeedback


@dataclass(frozen=True, slots=True)
class UserFeedbackTargetCohortCandidate:
    job_id: str
    feedback_id: str
    match_report_id: str
    decision: FeedbackDecision


@dataclass(frozen=True, slots=True)
class UserFeedbackTargetCohortSourceResult:
    candidates: tuple[UserFeedbackTargetCohortCandidate, ...]
    total_feedback_records: int
    latest_job_feedback_count: int
    excluded_rejected_job_ids: tuple[str, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class PersistenceReadinessCheck(Protocol):
    def __call__(self) -> UserFeedbackPersistenceReadiness: ...


class UserFeedbackTargetCohortSourceUseCase:
    """Expose traceable cohort candidates from each Job's latest real feedback."""

    def __init__(
        self,
        *,
        feedback_repository: AbstractUserFeedbackQueryRepository,
        persistence_readiness: PersistenceReadinessCheck,
    ) -> None:
        self._feedback_repository = feedback_repository
        self._persistence_readiness = persistence_readiness

    def execute(self) -> UserFeedbackTargetCohortSourceResult:
        readiness = self._persistence_readiness()
        if not readiness.ready:
            blockers = ", ".join(readiness.blocker_codes)
            raise UserFeedbackPersistenceNotReadyError(
                f"UserFeedback persistence schema is not ready: {blockers}"
            )

        feedback = self._feedback_repository.list_all()
        latest_by_job = _latest_feedback_by_job(feedback)

        interested: list[UserFeedbackTargetCohortCandidate] = []
        maybe: list[UserFeedbackTargetCohortCandidate] = []
        rejected: list[str] = []
        for job_id in sorted(latest_by_job):
            item = latest_by_job[job_id]
            decision = item.feedback.decision
            if decision is FeedbackDecision.REJECTED:
                rejected.append(job_id)
                continue

            candidate = UserFeedbackTargetCohortCandidate(
                job_id=job_id,
                feedback_id=item.id,
                match_report_id=item.feedback.match_report_id,
                decision=decision,
            )
            if decision is FeedbackDecision.INTERESTED:
                interested.append(candidate)
            else:
                maybe.append(candidate)

        return UserFeedbackTargetCohortSourceResult(
            candidates=tuple(interested + maybe),
            total_feedback_records=len(feedback),
            latest_job_feedback_count=len(latest_by_job),
            excluded_rejected_job_ids=tuple(rejected),
        )


def _latest_feedback_by_job(
    feedback: tuple[StoredUserFeedback, ...],
) -> dict[str, StoredUserFeedback]:
    latest: dict[str, StoredUserFeedback] = {}
    for item in feedback:
        job_id = item.feedback.job_id
        current = latest.get(job_id)
        if current is None or (item.created_at, item.id) > (current.created_at, current.id):
            latest[job_id] = item
    return latest


__all__ = [
    "UserFeedbackTargetCohortCandidate",
    "UserFeedbackTargetCohortSourceResult",
    "UserFeedbackTargetCohortSourceUseCase",
]
