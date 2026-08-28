"""HTTP contract tests for the read-only Match improvement endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_match_improvement_use_case
from app.application.match_improvement import MatchImprovement
from app.application.match_report import MatchRecommendation
from app.main import app


class _UseCase:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def execute(self, *, job_id: str, current_report_id: str) -> MatchImprovement:
        self.calls.append((job_id, current_report_id))
        return MatchImprovement(
            job_id=job_id,
            current_report_id=current_report_id,
            previous_report_id="report_prev",
            previous_recommendation=MatchRecommendation.BLOCKED,
            current_recommendation=MatchRecommendation.STRETCH,
            previous_missing_requirement_count=3,
            current_missing_requirement_count=1,
            resolved_requirement_ids=("req_1", "req_2"),
            newly_missing_requirement_ids=(),
            comparable=True,
        )


def test_match_improvement_api_exposes_read_only_delta() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_match_improvement_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/match-improvement",
                params={"jobId": "job_1", "currentReportId": "report_current"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "jobId": "job_1",
        "currentReportId": "report_current",
        "previousReportId": "report_prev",
        "previousRecommendation": "blocked",
        "currentRecommendation": "stretch",
        "previousMissingRequirementCount": 3,
        "currentMissingRequirementCount": 1,
        "resolvedRequirementIds": ["req_1", "req_2"],
        "newlyMissingRequirementIds": [],
        "comparable": True,
        "dbWrites": 0,
        "providerCalls": 0,
        "traceRunsCreated": 0,
    }
    assert use_case.calls == [("job_1", "report_current")]


def test_match_improvement_openapi_is_get_only() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/match-improvement"]["get"]

    assert "requestBody" not in operation
    assert {item["name"] for item in operation["parameters"]} == {"jobId", "currentReportId"}
