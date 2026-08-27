"""Guarded application orchestration for immutable UserFeedback writes."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.application.ports.match_report_repository import AbstractMatchReportQueryRepository
from app.application.ports.user_feedback_repository import AbstractUserFeedbackQueryRepository
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


class FeedbackMatchReportStaleError(ValueError):
    """Raised when feedback targets a MatchReport that is no longer current."""


class CurrentMatchReportQuery(Protocol):
    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        include_blocked: bool = False,
        top_n: int | None = None,
    ): ...


class PersistenceReadinessCheck(Protocol):
    def __call__(self) -> UserFeedbackPersistenceReadiness: ...


UserFeedbackUnitOfWorkFactory = Callable[[], AbstractUserFeedbackUnitOfWork]


@dataclass(frozen=True, slots=True)
class CreateUserFeedbackResult:
    feedback: StoredUserFeedback
    db_writes: int = 1
    provider_calls: int = 0
    trace_runs_created: int = 0


@dataclass(frozen=True, slots=True)
class ListUserFeedbackResult:
    feedback: tuple[StoredUserFeedback, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


@dataclass(frozen=True, slots=True)
class LatestUserFeedbackResult:
    latest_by_match_report: tuple[StoredUserFeedback, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class ListLatestUserFeedbackUseCase:
    """Return at most one latest immutable feedback record per requested MatchReport."""

    MAX_MATCH_REPORTS = 50

    def __init__(
        self,
        *,
        repository: AbstractUserFeedbackQueryRepository,
        persistence_readiness: PersistenceReadinessCheck,
    ) -> None:
        self._repository = repository
        self._persistence_readiness = persistence_readiness

    def execute(self, *, match_report_ids: tuple[str, ...]) -> LatestUserFeedbackResult:
        normalized = tuple(dict.fromkeys(item.strip() for item in match_report_ids if item.strip()))
        if not normalized:
            raise ValueError("at least one match_report_id is required")
        if len(normalized) > self.MAX_MATCH_REPORTS:
            raise ValueError("at most 50 match_report_ids are supported")

        readiness = self._persistence_readiness()
        if not readiness.ready:
            blockers = ", ".join(readiness.blocker_codes)
            raise UserFeedbackPersistenceNotReadyError(
                f"UserFeedback persistence schema is not ready: {blockers}"
            )

        requested = set(normalized)
        latest: dict[str, StoredUserFeedback] = {}
        for item in self._repository.list_all():
            report_id = item.feedback.match_report_id
            if report_id not in requested:
                continue
            previous = latest.get(report_id)
            if previous is None or (item.created_at, item.id) > (previous.created_at, previous.id):
                latest[report_id] = item
        return LatestUserFeedbackResult(
            latest_by_match_report=tuple(latest[item] for item in normalized if item in latest)
        )


class ListUserFeedbackUseCase:
    """Read immutable feedback history for exactly one provenance scope."""

    def __init__(
        self,
        *,
        repository: AbstractUserFeedbackQueryRepository,
        persistence_readiness: PersistenceReadinessCheck,
    ) -> None:
        self._repository = repository
        self._persistence_readiness = persistence_readiness

    def execute(
        self,
        *,
        match_report_id: str | None = None,
        job_id: str | None = None,
    ) -> ListUserFeedbackResult:
        normalized_match_report_id = match_report_id.strip() if match_report_id else None
        normalized_job_id = job_id.strip() if job_id else None
        if bool(normalized_match_report_id) == bool(normalized_job_id):
            raise ValueError("exactly one of match_report_id or job_id is required")

        readiness = self._persistence_readiness()
        if not readiness.ready:
            blockers = ", ".join(readiness.blocker_codes)
            raise UserFeedbackPersistenceNotReadyError(
                f"UserFeedback persistence schema is not ready: {blockers}"
            )

        if normalized_match_report_id is not None:
            feedback = self._repository.list_for_match_report(normalized_match_report_id)
        else:
            feedback = self._repository.list_for_job(normalized_job_id or "")
        return ListUserFeedbackResult(feedback=feedback)


class CreateUserFeedbackUseCase:
    """Validate provenance, then append one immutable feedback record."""

    def __init__(
        self,
        *,
        reports: AbstractMatchReportQueryRepository,
        current_reports: CurrentMatchReportQuery,
        persistence_readiness: PersistenceReadinessCheck,
        uow_factory: UserFeedbackUnitOfWorkFactory,
    ) -> None:
        self._reports = reports
        self._current_reports = current_reports
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
        normalized_job_id = job_id.strip()
        if report.report.job_id != normalized_job_id:
            raise FeedbackMatchReportMismatchError(
                "Feedback jobId must match the Job bound to the referenced MatchReport"
            )

        current_reports = self._current_reports.execute(
            (normalized_job_id,),
            include_blocked=True,
        )
        if not any(item.id == report.id for item in current_reports):
            raise FeedbackMatchReportStaleError(
                "Feedback must target the current MatchReport for the Job"
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
    "FeedbackMatchReportStaleError",
    "LatestUserFeedbackResult",
    "ListLatestUserFeedbackUseCase",
    "ListUserFeedbackResult",
    "ListUserFeedbackUseCase",
    "UserFeedbackPersistenceNotReadyError",
]
