"""HTTP contract tests for transient Semantic Match."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_semantic_match_use_case
from app.application.eligibility import EligibilityDecision, RequirementFitStatus
from app.application.semantic_match import (
    JobSemanticMatchResult,
    SemanticAssessmentSource,
    SemanticMatchInputsNotReadyError,
    SemanticMatchVerdict,
    SemanticRequirementAssessment,
)
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.main import app


class _UseCase:
    def execute(self, job_id: str) -> JobSemanticMatchResult:
        return JobSemanticMatchResult(
            job_id=job_id,
            profile_id="profile_1",
            profile_version=3,
            extraction_id="reqrun_1",
            eligibility=EligibilityDecision.BLOCKED,
            assessments=(
                SemanticRequirementAssessment(
                    requirement_id="req_mcp",
                    requirement_index=0,
                    type=RequirementType.SKILL,
                    importance=RequirementImportance.MUST_HAVE,
                    original_text="熟悉 MCP 协议",
                    normalized_capability="MCP",
                    eligibility_status=RequirementFitStatus.MISSING,
                    verdict=SemanticMatchVerdict.PARTIAL,
                    evidence_ids=("ev_tools",),
                    profile_fact_refs=(),
                    reason="相关工具调用经历，但没有直接 MCP 证据。",
                    source=SemanticAssessmentSource.PROVIDER,
                ),
            ),
            matched_count=0,
            partial_count=1,
            not_matched_count=0,
            matcher_version="semantic-match-v1",
            prompt_version="semantic-match-v1",
            model="fixture-semantic-matcher",
            trace_run_id="run_1",
            provider_calls=1,
            trace_runs_created=1,
        )


class _NotReadyUseCase:
    def execute(self, _job_id: str) -> JobSemanticMatchResult:
        raise SemanticMatchInputsNotReadyError("trusted match inputs changed")


def test_semantic_match_api_preserves_blocked_eligibility_and_partial_semantics() -> None:
    app.dependency_overrides[get_semantic_match_use_case] = _UseCase
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/jobs/job_1/semantic-match")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["eligibility"] == "blocked"
    assert body["partialCount"] == 1
    assert body["assessments"][0]["eligibilityStatus"] == "missing"
    assert body["assessments"][0]["verdict"] == "partial"
    assert body["assessments"][0]["evidenceIds"] == ["ev_tools"]
    assert body["providerCalls"] == 1
    assert body["traceRunsCreated"] == 1


def test_semantic_match_api_fails_closed_when_inputs_are_not_ready() -> None:
    app.dependency_overrides[get_semantic_match_use_case] = _NotReadyUseCase
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/jobs/job_1/semantic-match")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "semantic_match_inputs_not_ready"


def test_openapi_registers_semantic_match_as_side_effecting_post() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"][
            "/api/v1/jobs/{job_id}/semantic-match"
        ]["post"]

    assert "requestBody" not in operation
    assert "200" in operation["responses"]
    assert "409" in operation["responses"]
    assert "502" in operation["responses"]
    assert "503" in operation["responses"]
