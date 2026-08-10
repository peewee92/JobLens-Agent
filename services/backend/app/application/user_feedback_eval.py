"""Deterministic Match Eval observations derived from immutable UserFeedback history.

UserFeedback is an observed user preference signal, not objective match ground truth. This
module therefore reports distributions and coverage only; it never turns feedback into an
automatic quality gate or an accuracy/probability claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.match_report import MatchRecommendation, StoredMatchReport
from app.application.ports.match_report_repository import AbstractMatchReportQueryRepository
from app.application.ports.user_feedback_repository import AbstractUserFeedbackQueryRepository
from app.application.user_feedback import UserFeedbackPersistenceNotReadyError
from app.application.user_feedback_persistence import UserFeedbackPersistenceReadiness
from app.domain.user_feedback import FeedbackDecision, FeedbackReason, StoredUserFeedback


@dataclass(frozen=True, slots=True)
class UserFeedbackMatchEval:
    total_feedback_records: int
    latest_feedback_count: int
    evaluated_match_reports: int
    missing_match_report_ids: tuple[str, ...]
    decision_counts: dict[str, int]
    recommendation_decision_counts: dict[str, dict[str, int]]
    rejection_reason_counts: dict[str, int]
    quality_gate_applied: bool = False


@dataclass(frozen=True, slots=True)
class UserFeedbackMatchEvalQueryResult:
    eval: UserFeedbackMatchEval
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class PersistenceReadinessCheck(Protocol):
    def __call__(self) -> UserFeedbackPersistenceReadiness: ...


class UserFeedbackMatchEvalQueryUseCase:
    """Build read-only feedback observations for one Job's immutable MatchReports."""

    def __init__(
        self,
        *,
        feedback_repository: AbstractUserFeedbackQueryRepository,
        report_repository: AbstractMatchReportQueryRepository,
        persistence_readiness: PersistenceReadinessCheck,
    ) -> None:
        self._feedback_repository = feedback_repository
        self._report_repository = report_repository
        self._persistence_readiness = persistence_readiness

    def execute(self, *, job_id: str) -> UserFeedbackMatchEvalQueryResult:
        normalized_job_id = job_id.strip()
        if not normalized_job_id:
            raise ValueError("job_id is required")

        readiness = self._persistence_readiness()
        if not readiness.ready:
            blockers = ", ".join(readiness.blocker_codes)
            raise UserFeedbackPersistenceNotReadyError(
                f"UserFeedback persistence schema is not ready: {blockers}"
            )

        feedback = self._feedback_repository.list_for_job(normalized_job_id)
        reports = self._report_repository.list_for_job(normalized_job_id)
        return UserFeedbackMatchEvalQueryResult(
            eval=build_user_feedback_match_eval(feedback=feedback, reports=reports)
        )


def _latest_feedback_by_report(
    feedback: tuple[StoredUserFeedback, ...],
) -> dict[str, StoredUserFeedback]:
    latest: dict[str, StoredUserFeedback] = {}
    for item in feedback:
        report_id = item.feedback.match_report_id
        current = latest.get(report_id)
        if current is None or (item.created_at, item.id) > (current.created_at, current.id):
            latest[report_id] = item
    return latest


def _empty_decision_counts() -> dict[str, int]:
    return {decision.value: 0 for decision in FeedbackDecision}


def build_user_feedback_match_eval(
    *,
    feedback: tuple[StoredUserFeedback, ...],
    reports: tuple[StoredMatchReport, ...],
) -> UserFeedbackMatchEval:
    """Summarize latest user decisions against their exact immutable MatchReport.

    Multiple feedback records for one MatchReport represent history. Only the latest record
    contributes to current observed preference statistics, while the full history count is
    retained for auditability. Feedback whose MatchReport is unavailable is reported as
    missing and excluded rather than being guessed or joined by Job alone.
    """

    latest_by_report = _latest_feedback_by_report(feedback)
    reports_by_id = {report.id: report for report in reports}
    decision_counts = _empty_decision_counts()
    matrix = {
        recommendation.value: _empty_decision_counts()
        for recommendation in MatchRecommendation
    }
    reason_counts = {reason.value: 0 for reason in FeedbackReason}
    missing: list[str] = []
    evaluated = 0

    for report_id in sorted(latest_by_report):
        item = latest_by_report[report_id]
        report = reports_by_id.get(report_id)
        if report is None:
            missing.append(report_id)
            continue

        decision = item.feedback.decision.value
        recommendation = report.report.recommendation.value
        decision_counts[decision] += 1
        matrix[recommendation][decision] += 1
        evaluated += 1

        if item.feedback.decision is FeedbackDecision.REJECTED:
            for reason in item.feedback.reasons:
                reason_counts[reason.value] += 1

    observed_reasons = {
        reason.value: reason_counts[reason.value]
        for reason in FeedbackReason
        if reason_counts[reason.value] > 0
    }

    return UserFeedbackMatchEval(
        total_feedback_records=len(feedback),
        latest_feedback_count=len(latest_by_report),
        evaluated_match_reports=evaluated,
        missing_match_report_ids=tuple(missing),
        decision_counts=decision_counts,
        recommendation_decision_counts=matrix,
        rejection_reason_counts=observed_reasons,
    )


__all__ = [
    "UserFeedbackMatchEval",
    "UserFeedbackMatchEvalQueryResult",
    "UserFeedbackMatchEvalQueryUseCase",
    "build_user_feedback_match_eval",
]
