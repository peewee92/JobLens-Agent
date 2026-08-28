"""HTTP contract tests for the read-only Match improvement endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_match_improvement_use_case
from app.application.match_improvement import MatchImprovement, MatchImprovementEvidenceImpact, MatchImprovementRequirement
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
            previous_profile_version=2,
            current_profile_version=3,
            previous_missing_requirement_count=3,
            current_missing_requirement_count=1,
            resolved_requirement_ids=("req_1", "req_2"),
            newly_missing_requirement_ids=(),
            resolved_requirements=(
                MatchImprovementRequirement(requirement_id="req_1", original_text="本科及以上学历"),
                MatchImprovementRequirement(requirement_id="req_2", original_text="熟悉 Python"),
            ),
            newly_missing_requirements=(),
            newly_supporting_evidence=(
                MatchImprovementEvidenceImpact(
                    evidence_id="evidence_1",
                    evidence_type="project",
                    summary="在真实项目中使用 Python 构建数据处理服务",
                    supporting_requirements=(
                        MatchImprovementRequirement(requirement_id="req_2", original_text="熟悉 Python"),
                    ),
                ),
            ),
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
        "previousProfileVersion": 2,
        "currentProfileVersion": 3,
        "previousMissingRequirementCount": 3,
        "currentMissingRequirementCount": 1,
        "resolvedRequirementIds": ["req_1", "req_2"],
        "newlyMissingRequirementIds": [],
        "resolvedRequirements": [
            {"requirementId": "req_1", "originalText": "本科及以上学历"},
            {"requirementId": "req_2", "originalText": "熟悉 Python"},
        ],
        "newlyMissingRequirements": [],
        "newlySupportingEvidence": [
            {
                "evidenceId": "evidence_1",
                "evidenceType": "project",
                "summary": "在真实项目中使用 Python 构建数据处理服务",
                "supportingRequirements": [
                    {"requirementId": "req_2", "originalText": "熟悉 Python"},
                ],
            }
        ],
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
