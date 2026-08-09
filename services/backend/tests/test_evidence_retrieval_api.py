"""HTTP contract tests for deterministic Evidence Retrieval."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_job_evidence_retrieval_use_case
from app.application.evidence_retrieval import (
    CandidateEvidence,
    EvidenceRelevanceTier,
    EvidenceRetrievalBasis,
    EvidenceRetrievalInputsNotReadyError,
    JobEvidenceRetrievalResult,
    RequirementEvidenceCandidates,
)
from app.domain.career_context import EvidenceType
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.main import app


class _UseCase:
    def execute(self, job_id: str) -> JobEvidenceRetrievalResult:
        return JobEvidenceRetrievalResult(
            job_id=job_id,
            profile_id="profile_1",
            profile_version=3,
            extraction_id="reqrun_1",
            requirements=(
                RequirementEvidenceCandidates(
                    requirement_id="req_mcp",
                    requirement_index=0,
                    type=RequirementType.SKILL,
                    importance=RequirementImportance.MUST_HAVE,
                    original_text="熟悉 MCP 协议",
                    normalized_capability="MCP",
                    candidates=(
                        CandidateEvidence(
                            evidence_id="ev_tools",
                            evidence_key="agent-tools",
                            evidence_type=EvidenceType.PROJECT,
                            summary="设计 Agent 工具调用、Function Calling 与工具集成。",
                            source="confirmed by user",
                            relevance_tier=EvidenceRelevanceTier.RELATED,
                            retrieval_basis=EvidenceRetrievalBasis.RELATED_CAPABILITY_HINT,
                            matched_terms=("Function Calling", "工具调用", "工具集成"),
                            reason="只能作为相关候选，不能因此认定已经满足岗位要求。",
                        ),
                    ),
                ),
            ),
            candidate_count=1,
        )


class _NotReadyUseCase:
    def execute(self, _job_id: str) -> JobEvidenceRetrievalResult:
        raise EvidenceRetrievalInputsNotReadyError("trusted inputs are not ready")


def test_evidence_retrieval_api_returns_candidate_evidence_without_match_verdicts() -> None:
    app.dependency_overrides[get_job_evidence_retrieval_use_case] = _UseCase
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/jobs/job_1/evidence-candidates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["jobId"] == "job_1"
    assert body["profileVersion"] == 3
    assert body["candidateCount"] == 1
    candidate = body["requirements"][0]["candidates"][0]
    assert candidate["evidenceId"] == "ev_tools"
    assert candidate["relevanceTier"] == "related"
    assert candidate["retrievalBasis"] == "related_capability_hint"
    assert "Function Calling" in candidate["matchedTerms"]
    assert "status" not in candidate
    assert "matched" not in candidate
    assert body["dbWrites"] == 0
    assert body["providerCalls"] == 0
    assert body["traceRunsCreated"] == 0


def test_evidence_retrieval_api_fails_closed_when_trusted_inputs_are_not_ready() -> None:
    app.dependency_overrides[get_job_evidence_retrieval_use_case] = _NotReadyUseCase
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/jobs/job_1/evidence-candidates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "evidence_retrieval_inputs_not_ready"


def test_openapi_registers_evidence_retrieval_as_read_only_get() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"][
            "/api/v1/jobs/{job_id}/evidence-candidates"
        ]["get"]

    assert "requestBody" not in operation
    assert "200" in operation["responses"]
    assert "409" in operation["responses"]
