"""HTTP contract tests for transient MatchReport."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_match_report_use_case
from app.application.eligibility import EligibilityDecision, RequirementFitStatus
from app.application.match_report import (
    MatchEvidenceLink,
    MatchRecommendation,
    MatchReport,
    MatchReportInsight,
    MatchReportRequirementResult,
)
from app.application.semantic_match import SemanticMatchVerdict
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.main import app


class _UseCase:
    def execute(self, job_id: str) -> MatchReport:
        requirement = MatchReportRequirementResult(
            requirement_id="req_mcp",
            requirement_index=0,
            type=RequirementType.SKILL,
            importance=RequirementImportance.MUST_HAVE,
            original_text="熟悉 MCP 协议",
            normalized_capability="MCP",
            eligibility_status=RequirementFitStatus.MISSING,
            semantic_verdict=SemanticMatchVerdict.PARTIAL,
            evidence_ids=("ev_tools",),
            profile_fact_refs=(),
            reason="工具调用经历相关，但没有直接 MCP 证据。",
        )
        risk = MatchReportInsight(
            requirement_id="req_mcp",
            requirement_text="熟悉 MCP 协议",
            reason=requirement.reason,
            evidence_ids=("ev_tools",),
        )
        return MatchReport(
            job_id=job_id,
            profile_id="profile_1",
            profile_version=3,
            extraction_id="reqrun_1",
            eligibility=EligibilityDecision.BLOCKED,
            recommendation=MatchRecommendation.BLOCKED,
            summary="存在明确硬条件缺口，当前不建议优先投入。",
            strengths=(),
            risks=(risk,),
            requirement_results=(requirement,),
            matched_requirement_ids=(),
            partial_requirement_ids=("req_mcp",),
            missing_requirement_ids=("req_mcp",),
            evidence_links=(
                MatchEvidenceLink(
                    requirement_id="req_mcp",
                    evidence_ids=("ev_tools",),
                ),
            ),
            matcher_version="semantic-match-v1",
            prompt_version="semantic-match-v1",
            model="fixture-semantic-matcher",
            trace_run_id="run_1",
            provider_calls=1,
            trace_runs_created=1,
        )


def test_match_report_api_returns_recommendation_and_traceable_evidence() -> None:
    app.dependency_overrides[get_match_report_use_case] = _UseCase
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/jobs/job_1/match-report")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["eligibility"] == "blocked"
    assert body["recommendation"] == "blocked"
    assert body["partialRequirementIds"] == ["req_mcp"]
    assert body["missingRequirementIds"] == ["req_mcp"]
    assert body["risks"][0]["requirementId"] == "req_mcp"
    assert body["evidenceLinks"][0]["evidenceIds"] == ["ev_tools"]
    assert "score" not in body
    assert body["dbWrites"] == 0
    assert body["providerCalls"] == 1
    assert body["traceRunsCreated"] == 1


def test_openapi_registers_match_report_as_explicit_post_without_request_body() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"][
            "/api/v1/jobs/{job_id}/match-report"
        ]["post"]

    assert "requestBody" not in operation
    assert "200" in operation["responses"]
    assert "409" in operation["responses"]
    assert "502" in operation["responses"]
    assert "503" in operation["responses"]
