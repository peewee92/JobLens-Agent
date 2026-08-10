"""Guarded application orchestration for immutable UserFeedback writes."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.application.ports.match_report_repository import AbstractMatchReportQueryRepository
from app.application.ports.user_feedback_unit_of_work import AbstractUserFeedbackUnitOfWork
from app.application.user_feedback_persistence import UserFeedbackPersistenceReadiness
from app.domain.user_feedback import (
    FeedbackDecision,
    FeedbackReason,
    StoredUserFeedback,
    UserFeedbackDraft,
)


class UserFeedbackPersistenceNotReadyError(RuntimeError):
    """Raised before any feedback read/write when persistence schema is unavailable."""


class FeedbackMatchReportNotFoundError(LookupError):
    """Raised when feedback references an unknown immutable MatchReport."""


class FeedbackMatchReportMismatchError(ValueError):
    """Raised when a MatchReport belongs to a different Job."""


class PersistenceReadinessCheck(Protocol):
    def __call__(self) -> UserFeedbackPersistenceReadiness: ...


UserFeedbackUnitOfWorkFactory = Callable[[], AbstractUserFeedbackUnitOfWork]


@dataclass(frozen=True, slots=True)
class CreateUserFeedbackResult:
    feedback: StoredUserFeedback
    db_writes: int = 1
    provider_calls: int = 0
    trace_runs_created: int = 0


class CreateUserFeedbackUseCase:
    """Validate provenance, then append one immutable feedback record."""

    def __init__(
        self,
        *,
        reports: AbstractMatchReportQueryRepository,
        persistence_readiness: PersistenceReadinessCheck,
        uow_factory: UserFeedbackUnitOfWorkFactory,
    ) -> None:
        self._reports = reports
        self._persistence_readiness = persistence_readiness
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        match_report_id: str,
        job_id: str,
        decision: FeedbackDecision,
        reasons: tuple[FeedbackReason, ...] = (),
        note: str | None = None,
    ) -> CreateUserFeedbackResult:
        readiness = self._persistence_readiness()
        if not readiness.ready:
            blockers = ", ".join(readiness.blocker_codes)
            raise UserFeedbackPersistenceNotReadyError(
                f"UserFeedback persistence schema is not ready: {blockers}"
            )

        report = self._reports.get(match_report_id.strip())
        if report is None:
            raise FeedbackMatchReportNotFoundError(
                f"MatchReport {match_report_id!r} was not found"
            )
        if report.report.job_id != job_id.strip():
            raise FeedbackMatchReportMismatchError(
                "Feedback jobId must match the Job bound to the referenced MatchReport"
            )

        draft = UserFeedbackDraft.create(
            match_report_id=match_report_id,
            job_id=job_id,
            decision=decision,
            reasons=reasons,
            note=note,
        )
        with self._uow_factory() as uow:
            stored = uow.feedback.add(draft)
            uow.commit()
        return CreateUserFeedbackResult(feedback=stored)


__all__ = [
    "CreateUserFeedbackResult",
    "CreateUserFeedbackUseCase",
    "FeedbackMatchReportMismatchError",
    "FeedbackMatchReportNotFoundError",
    "UserFeedbackPersistenceNotReadyError",
]
