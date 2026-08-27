"""HTTP contract tests for the read-only Match blocker summary."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_match_blocker_summary_use_case
from app.application.match_blocker_summary import (
    MatchBlockerCategorySummary,
    MatchBlockerJobSummary,
    MatchBlockerRequirementSummary,
    MatchBlockerSummary,
)
from app.domain.job_requirements import RequirementType
from app.main import app


class _UseCase:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def execute(self, job_ids: tuple[str, ...]) -> MatchBlockerSummary:
        self.calls.append(job_ids)
        return MatchBlockerSummary(
            analyzed_report_count=2,
            blocked_report_count=2,
            missing_requirement_count=3,
            resolved_missing_requirement_count=3,
            unresolved_missing_requirement_ids=(),
            categories=(
                MatchBlockerCategorySummary(
                    requirement_type=RequirementType.EDUCATION,
                    missing_requirement_count=2,
                    affected_job_count=2,
                    affected_job_ids=("job_1", "job_2"),
                    examples=("本科及以上学历", "计算机相关专业本科及以上"),
                ),
                MatchBlockerCategorySummary(
                    requirement_type=RequirementType.SKILL,
                    missing_requirement_count=1,
                    affected_job_count=1,
                    affected_job_ids=("job_2",),
                    examples=("熟练使用 Python",),
                ),
            ),
            job_blockers=(
                MatchBlockerJobSummary(
                    job_id="job_1",
                    missing_requirement_count=1,
                    requirements=(
                        MatchBlockerRequirementSummary(
                            requirement_id="edu_1",
                            requirement_type=RequirementType.EDUCATION,
                            original_text="本科及以上学历",
                        ),
                    ),
                    unresolved_missing_requirement_ids=(),
                ),
                MatchBlockerJobSummary(
                    job_id="job_2",
                    missing_requirement_count=2,
                    requirements=(
                        MatchBlockerRequirementSummary(
                            requirement_id="edu_2",
                            requirement_type=RequirementType.EDUCATION,
                            original_text="计算机相关专业本科及以上",
                        ),
                        MatchBlockerRequirementSummary(
                            requirement_id="skill_1",
                            requirement_type=RequirementType.SKILL,
                            original_text="熟练使用 Python",
                        ),
                    ),
                    unresolved_missing_requirement_ids=(),
                ),
            ),
        )


def test_match_blocker_summary_api_exposes_read_only_profile_evidence_gaps() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_match_blocker_summary_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/match-blockers",
                params=[("jobId", "job_1"), ("jobId", "job_2")],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["analyzedReportCount"] == 2
    assert body["blockedReportCount"] == 2
    assert body["missingRequirementCount"] == 3
    assert body["resolvedMissingRequirementCount"] == 3
    assert body["unresolvedMissingRequirementIds"] == []
    assert body["categories"][0] == {
        "requirementType": "education",
        "missingRequirementCount": 2,
        "affectedJobCount": 2,
        "affectedJobIds": ["job_1", "job_2"],
        "examples": ["本科及以上学历", "计算机相关专业本科及以上"],
    }
    assert body["jobBlockers"][1] == {
        "jobId": "job_2",
        "missingRequirementCount": 2,
        "requirements": [
            {
                "requirementId": "edu_2",
                "requirementType": "education",
                "originalText": "计算机相关专业本科及以上",
            },
            {
                "requirementId": "skill_1",
                "requirementType": "skill",
                "originalText": "熟练使用 Python",
            },
        ],
        "unresolvedMissingRequirementIds": [],
    }
    assert body["dbWrites"] == 0
    assert body["providerCalls"] == 0
    assert body["traceRunsCreated"] == 0
    assert use_case.calls == [("job_1", "job_2")]


def test_match_blocker_summary_api_requires_job_ids() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/match-blockers")

    assert response.status_code == 422


def test_openapi_registers_match_blocker_summary_as_read_only_get() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/match-blockers"]["get"]

    assert "requestBody" not in operation
    assert {item["name"] for item in operation["parameters"]} == {"jobId"}
