"""HTTP contract tests for the read-only recommendation coverage planner."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_recommendation_coverage_use_case
from app.application.recommendation_coverage import (
    RecommendationCoverage,
    RecommendationCoverageCandidate,
    RecommendationCoverageStatus,
)
from app.main import app


class _UseCase:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self) -> RecommendationCoverage:
        self.calls += 1
        return RecommendationCoverage(
            total_job_count=20,
            considered_job_count=20,
            current_report_count=4,
            match_ready_without_report_count=2,
            requirement_analysis_needed_count=10,
            profile_blocked_count=3,
            other_blocked_count=1,
            next_analysis_candidates=(
                RecommendationCoverageCandidate(
                    job_id="job_fde",
                    title="前沿部署工程师(FDE)",
                    company="Example AI",
                    area="武汉",
                    salary_min_k=20,
                    salary_max_k=35,
                    status=RecommendationCoverageStatus.REQUIREMENT_ANALYSIS_NEEDED,
                    blocker_codes=("accepted_baseline_missing",),
                    intent_signals=("目标方向：FDE", "目标城市：武汉", "薪资下限达到 14K"),
                ),
            ),
        )


def test_recommendation_coverage_api_exposes_read_only_next_analysis_queue() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_recommendation_coverage_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/recommendation-coverage")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["totalJobCount"] == 20
    assert body["consideredJobCount"] == 20
    assert body["currentReportCount"] == 4
    assert body["matchReadyWithoutReportCount"] == 2
    assert body["requirementAnalysisNeededCount"] == 10
    assert body["profileBlockedCount"] == 3
    assert body["otherBlockedCount"] == 1
    assert body["nextAnalysisCandidates"] == [
        {
            "jobId": "job_fde",
            "title": "前沿部署工程师(FDE)",
            "company": "Example AI",
            "area": "武汉",
            "salaryMinK": 20.0,
            "salaryMaxK": 35.0,
            "status": "requirement_analysis_needed",
            "blockerCodes": ["accepted_baseline_missing"],
            "intentSignals": ["目标方向：FDE", "目标城市：武汉", "薪资下限达到 14K"],
        }
    ]
    assert body["dbWrites"] == 0
    assert body["providerCalls"] == 0
    assert body["traceRunsCreated"] == 0
    assert use_case.calls == 1


def test_openapi_registers_recommendation_coverage_as_read_only_get() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/recommendation-coverage"]["get"]

    assert "requestBody" not in operation
    assert operation.get("parameters", []) == []
