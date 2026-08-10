"""Application tests for guarded immutable UserFeedback writes."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.application.user_feedback import (
    CreateUserFeedbackUseCase,
    FeedbackMatchReportMismatchError,
    FeedbackMatchReportNotFoundError,
    UserFeedbackPersistenceNotReadyError,
)
from app.domain.user_feedback import FeedbackDecision, FeedbackReason, StoredUserFeedback


class _Reports:
    def __init__(self, report=None) -> None:
        self.report = report
        self.calls: list[str] = []

    def get(self, report_id: str):
        self.calls.append(report_id)
        return self.report


class _FeedbackRepo:
    def __init__(self) -> None:
        self.added = []

    def add(self, draft):
        self.added.append(draft)
        return StoredUserFeedback(
            id="feedback_1",
            feedback=draft,
            created_at=datetime(2026, 8, 10, tzinfo=UTC),
        )


class _Uow:
    def __init__(self) -> None:
        self.feedback = _FeedbackRepo()
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None


def _report(job_id: str = "job_1"):
    return SimpleNamespace(id="report_1", report=SimpleNamespace(job_id=job_id))


def test_create_user_feedback_persists_one_immutable_record() -> None:
    reports = _Reports(_report())
    uow = _Uow()
    use_case = CreateUserFeedbackUseCase(
        reports=reports,
        persistence_readiness=lambda: SimpleNamespace(ready=True, blocker_codes=()),
        uow_factory=lambda: uow,
    )

    result = use_case.execute(
        match_report_id="report_1",
        job_id="job_1",
        decision=FeedbackDecision.REJECTED,
        reasons=(FeedbackReason.SKILL_GAP,),
        note="Need stronger evidence.",
    )

    assert result.feedback.id == "feedback_1"
    assert result.db_writes == 1
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0
    assert reports.calls == ["report_1"]
    assert len(uow.feedback.added) == 1
    assert uow.commits == 1


def test_create_user_feedback_fails_before_queries_or_writes_when_schema_not_ready() -> None:
    reports = _Reports(_report())
    uow = _Uow()
    use_case = CreateUserFeedbackUseCase(
        reports=reports,
        persistence_readiness=lambda: SimpleNamespace(
            ready=False,
            blocker_codes=("match_report_persistence_not_ready", "user_feedback_persistence_not_ready"),
        ),
        uow_factory=lambda: uow,
    )

    with pytest.raises(UserFeedbackPersistenceNotReadyError):
        use_case.execute(
            match_report_id="report_1",
            job_id="job_1",
            decision=FeedbackDecision.INTERESTED,
        )

    assert reports.calls == []
    assert uow.feedback.added == []
    assert uow.commits == 0


def test_create_user_feedback_rejects_missing_match_report() -> None:
    reports = _Reports(None)
    uow = _Uow()
    use_case = CreateUserFeedbackUseCase(
        reports=reports,
        persistence_readiness=lambda: SimpleNamespace(ready=True, blocker_codes=()),
        uow_factory=lambda: uow,
    )

    with pytest.raises(FeedbackMatchReportNotFoundError):
        use_case.execute(
            match_report_id="report_missing",
            job_id="job_1",
            decision=FeedbackDecision.INTERESTED,
        )

    assert uow.feedback.added == []
    assert uow.commits == 0


def test_create_user_feedback_rejects_job_binding_mismatch() -> None:
    reports = _Reports(_report(job_id="job_other"))
    uow = _Uow()
    use_case = CreateUserFeedbackUseCase(
        reports=reports,
        persistence_readiness=lambda: SimpleNamespace(ready=True, blocker_codes=()),
        uow_factory=lambda: uow,
    )

    with pytest.raises(FeedbackMatchReportMismatchError):
        use_case.execute(
            match_report_id="report_1",
            job_id="job_1",
            decision=FeedbackDecision.INTERESTED,
        )

    assert uow.feedback.added == []
    assert uow.commits == 0
