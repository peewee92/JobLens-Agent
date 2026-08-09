"""HTTP contract tests for deterministic Eligibility."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_job_eligibility_use_case
from app.application.eligibility import (
    EligibilityDecision,
    EligibilityInputsNotReadyError,
    JobEligibilityResult,
    RequirementEligibilityResult,
    RequirementFitStatus,
)
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.main import app


class _UseCase:
    def execute(self, job_id: str) -> JobEligibilityResult:
        return JobEligibilityResult(
            job_id=job_id,
            profile_id="profile_1",
            profile_version=2,
            extraction_id="reqrun_1",
            eligibility=EligibilityDecision.BLOCKED,
            requirements=(
                RequirementEligibilityResult(
                    requirement_id="req_java",
                    requirement_index=0,
                    type=RequirementType.SKILL,
                    importance=RequirementImportance.MUST_HAVE,
                    original_text="精通 Java",
                    normalized_capability="Java",
                    status=RequirementFitStatus.MISSING,
                    evidence_ids=(),
                    profile_fact_refs=(),
                    reason="这是岗位明确的硬技能要求，但当前已确认技能和经历中没有对应证据。",
                ),
            ),
            matched_count=0,
            conditional_count=0,
            missing_count=1,
        )


class _NotReadyUseCase:
    def execute(self, _job_id: str) -> JobEligibilityResult:
        raise EligibilityInputsNotReadyError("trusted inputs are not ready")


def test_eligibility_api_returns_explainable_requirement_results() -> None:
    app.dependency_overrides[get_job_eligibility_use_case] = _UseCase
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/jobs/job_1/eligibility")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["eligibility"] == "blocked"
    assert body["profileVersion"] == 2
    assert body["extractionId"] == "reqrun_1"
    assert body["missingCount"] == 1
    assert body["requirements"][0]["status"] == "missing"
    assert body["requirements"][0]["requirementId"] == "req_java"
    assert body["requirements"][0]["evidenceIds"] == []
    assert body["dbWrites"] == 0
    assert body["providerCalls"] == 0
    assert body["traceRunsCreated"] == 0


def test_eligibility_api_fails_closed_when_trusted_inputs_are_not_ready() -> None:
    app.dependency_overrides[get_job_eligibility_use_case] = _NotReadyUseCase
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/jobs/job_1/eligibility")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "eligibility_inputs_not_ready"


def test_openapi_registers_eligibility_as_read_only_get() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"][
            "/api/v1/jobs/{job_id}/eligibility"
        ]["get"]

    assert "requestBody" not in operation
    assert "200" in operation["responses"]
    assert "409" in operation["responses"]
