"""Read-only UserFeedback history query tests."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_list_latest_user_feedback_use_case, get_list_user_feedback_use_case
from app.application.user_feedback import (
    LatestUserFeedbackResult,
    ListLatestUserFeedbackUseCase,
    ListUserFeedbackResult,
    ListUserFeedbackUseCase,
    UserFeedbackPersistenceNotReadyError,
)
from app.application.user_feedback_persistence import UserFeedbackPersistenceReadiness
from app.domain.user_feedback import (
    FeedbackDecision,
    FeedbackReason,
    StoredUserFeedback,
    UserFeedbackDraft,
)
from app.main import app


class _FeedbackQueries:
    def __init__(self, items: tuple[StoredUserFeedback, ...]) -> None:
        self.items = items
        self.match_report_calls: list[str] = []
        self.job_calls: list[str] = []

    def get(self, feedback_id: str):
        return None

    def list_for_match_report(self, match_report_id: str):
        self.match_report_calls.append(match_report_id)
        return self.items

    def list_for_job(self, job_id: str):
        self.job_calls.append(job_id)
        return self.items

    def list_all(self):
        return self.items


def _stored() -> StoredUserFeedback:
    return StoredUserFeedback(
        id="feedback_1",
        feedback=UserFeedbackDraft.create(
            match_report_id="report_1",
            job_id="job_1",
            decision=FeedbackDecision.INTERESTED,
        ),
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
    )


def _ready() -> UserFeedbackPersistenceReadiness:
    return UserFeedbackPersistenceReadiness(ready=True, blocker_codes=())


def _not_ready() -> UserFeedbackPersistenceReadiness:
    return UserFeedbackPersistenceReadiness(
        ready=False,
        blocker_codes=(
            "match_report_persistence_not_ready",
            "user_feedback_persistence_not_ready",
        ),
    )


def test_list_feedback_for_match_report_is_read_only() -> None:
    queries = _FeedbackQueries((_stored(),))
    result = ListUserFeedbackUseCase(
        repository=queries,
        persistence_readiness=_ready,
    ).execute(match_report_id=" report_1 ")

    assert [item.id for item in result.feedback] == ["feedback_1"]
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0
    assert queries.match_report_calls == ["report_1"]
    assert queries.job_calls == []


def test_list_feedback_for_job_is_read_only() -> None:
    queries = _FeedbackQueries((_stored(),))
    result = ListUserFeedbackUseCase(
        repository=queries,
        persistence_readiness=_ready,
    ).execute(job_id=" job_1 ")

    assert len(result.feedback) == 1
    assert queries.job_calls == ["job_1"]
    assert queries.match_report_calls == []


def test_list_latest_feedback_returns_one_record_per_requested_report() -> None:
    older = _stored()
    newer = StoredUserFeedback(
        id="feedback_2",
        feedback=UserFeedbackDraft.create(
            match_report_id="report_1",
            job_id="job_1",
            decision=FeedbackDecision.REJECTED,
            reasons=(FeedbackReason.ROLE_FIT,),
        ),
        created_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    other = StoredUserFeedback(
        id="feedback_3",
        feedback=UserFeedbackDraft.create(
            match_report_id="report_2",
            job_id="job_2",
            decision=FeedbackDecision.MAYBE,
        ),
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
    )
    result = ListLatestUserFeedbackUseCase(
        repository=_FeedbackQueries((older, newer, other)),
        persistence_readiness=_ready,
    ).execute(match_report_ids=("report_2", "report_1", "report_1"))

    assert [(item.feedback.match_report_id, item.feedback.decision) for item in result.latest_by_match_report] == [
        ("report_2", FeedbackDecision.MAYBE),
        ("report_1", FeedbackDecision.REJECTED),
    ]
    assert result.db_writes == result.provider_calls == result.trace_runs_created == 0


def test_list_feedback_requires_exactly_one_scope() -> None:
    use_case = ListUserFeedbackUseCase(
        repository=_FeedbackQueries(()),
        persistence_readiness=_ready,
    )

    with pytest.raises(ValueError, match="exactly one"):
        use_case.execute()
    with pytest.raises(ValueError, match="exactly one"):
        use_case.execute(match_report_id="report_1", job_id="job_1")


def test_list_feedback_fails_closed_before_query_when_schema_missing() -> None:
    queries = _FeedbackQueries(())
    use_case = ListUserFeedbackUseCase(
        repository=queries,
        persistence_readiness=_not_ready,
    )

    with pytest.raises(UserFeedbackPersistenceNotReadyError):
        use_case.execute(job_id="job_1")

    assert queries.job_calls == []
    assert queries.match_report_calls == []


class _UseCase:
    def execute(self, **kwargs):
        assert kwargs == {"match_report_id": "report_1", "job_id": None}
        return ListUserFeedbackResult(feedback=(_stored(),))


class _LatestUseCase:
    def execute(self, **kwargs):
        assert kwargs == {"match_report_ids": ("report_1", "report_2")}
        return LatestUserFeedbackResult(latest_by_match_report=(_stored(),))


def test_latest_user_feedback_api_returns_batch_read_model() -> None:
    app.dependency_overrides[get_list_latest_user_feedback_use_case] = lambda: _LatestUseCase()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/user-feedback/latest",
                params=[("matchReportId", "report_1"), ("matchReportId", "report_2")],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["feedback"][0]["feedbackId"] == "feedback_1"
    assert body["dbWrites"] == body["providerCalls"] == body["traceRunsCreated"] == 0


def test_user_feedback_history_api_returns_read_only_history() -> None:
    app.dependency_overrides[get_list_user_feedback_use_case] = lambda: _UseCase()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/user-feedback",
                params={"matchReportId": "report_1"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["feedback"][0]["feedbackId"] == "feedback_1"
    assert body["dbWrites"] == 0
    assert body["providerCalls"] == 0
    assert body["traceRunsCreated"] == 0


def test_user_feedback_history_api_requires_one_scope() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/user-feedback")
    assert response.status_code == 422


def test_user_feedback_history_real_schema_fails_closed() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/user-feedback",
            params={"jobId": "job_1"},
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "user_feedback_persistence_not_ready"
