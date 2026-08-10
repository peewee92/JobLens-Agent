"""HTTP contract tests for guarded immutable UserFeedback collection."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.deps import get_create_user_feedback_use_case
from app.application.user_feedback import CreateUserFeedbackResult
from app.domain.user_feedback import FeedbackDecision, FeedbackReason, StoredUserFeedback, UserFeedbackDraft
from app.main import app


class _UseCase:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        draft = UserFeedbackDraft.create(
            match_report_id=kwargs["match_report_id"],
            job_id=kwargs["job_id"],
            decision=kwargs["decision"],
            reasons=kwargs["reasons"],
            note=kwargs["note"],
        )
        return CreateUserFeedbackResult(
            feedback=StoredUserFeedback(
                id="feedback_1",
                feedback=draft,
                created_at=datetime(2026, 8, 10, tzinfo=UTC),
            )
        )


def test_user_feedback_api_returns_created_immutable_record() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_create_user_feedback_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/user-feedback",
                json={
                    "matchReportId": "report_1",
                    "jobId": "job_1",
                    "decision": "rejected",
                    "reasons": ["skill_gap"],
                    "note": "Need stronger evidence.",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["feedbackId"] == "feedback_1"
    assert body["matchReportId"] == "report_1"
    assert body["decision"] == "rejected"
    assert body["reasons"] == ["skill_gap"]
    assert body["dbWrites"] == 1
    assert body["providerCalls"] == 0
    assert body["traceRunsCreated"] == 0
    assert use_case.calls[0]["decision"] is FeedbackDecision.REJECTED
    assert use_case.calls[0]["reasons"] == (FeedbackReason.SKILL_GAP,)


def test_user_feedback_api_rejects_invalid_enum_before_use_case() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_create_user_feedback_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/user-feedback",
                json={
                    "matchReportId": "report_1",
                    "jobId": "job_1",
                    "decision": "liked",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert use_case.calls == []


def test_user_feedback_api_rejects_invalid_domain_combination_before_use_case() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_create_user_feedback_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/user-feedback",
                json={
                    "matchReportId": "report_1",
                    "jobId": "job_1",
                    "decision": "rejected",
                    "reasons": [],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert use_case.calls == []


def test_user_feedback_api_real_schema_fails_closed_before_write() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/user-feedback",
            json={
                "matchReportId": "report_missing",
                "jobId": "job_1",
                "decision": "interested",
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "user_feedback_persistence_not_ready"
