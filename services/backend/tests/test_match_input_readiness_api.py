"""HTTP contract tests for Match input preflight."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.deps import get_match_input_readiness_use_case
from app.application.career_context.release import CareerContextReleaseReadiness
from app.application.job_requirements.release import JobRequirementReleaseReadiness
from app.application.match_inputs.readiness import MatchInputReadiness
from app.main import app


class _UseCase:
    def execute(self, job_id: str) -> MatchInputReadiness:
        now = datetime(2026, 8, 5, tzinfo=UTC)
        career = CareerContextReleaseReadiness(
            release_eligible=True,
            confirmation_boundary="explicit_versioned_user_confirmation",
            profile_id="prof_1",
            profile_version=2,
            profile_created_at=now,
            profile_evidence_count=3,
            profile_skill_count=2,
            search_intent_id="intent_1",
            search_intent_version=1,
            search_intent_created_at=now,
            search_intent_target_role_count=2,
            blockers=(),
        )
        requirements = JobRequirementReleaseReadiness(
            job_id=job_id,
            release_eligible=True,
            current_description_sha256="abc",
            extraction_id="reqrun_1",
            extraction_input_hash="abc",
            provider="openai",
            model="model",
            extractor_version="v1",
            prompt_version="p1",
            trace_run_id="run_1",
            requirement_count=4,
            accepted_baseline_batch_id="batch_1",
            accepted_baseline_decision_id="decision_1",
            accepted_baseline_evidence_fingerprint="fingerprint",
            blockers=(),
        )
        return MatchInputReadiness(
            job_id=job_id,
            inputs_release_eligible=True,
            career_context=career,
            job_requirements=requirements,
            blockers=(),
        )


def test_match_input_readiness_api_returns_nested_frozen_fact_identities() -> None:
    app.dependency_overrides[get_match_input_readiness_use_case] = _UseCase
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/jobs/job_1/match-input-readiness")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["jobId"] == "job_1"
    assert body["inputsReleaseEligible"] is True
    assert body["careerContext"]["profileVersion"] == 2
    assert body["careerContext"]["searchIntentVersion"] == 1
    assert body["jobRequirements"]["extractionId"] == "reqrun_1"
    assert body["jobRequirements"]["traceRunId"] == "run_1"
    assert body["dbWrites"] == 0
    assert body["providerCalls"] == 0
    assert body["traceRunsCreated"] == 0


def test_openapi_registers_match_input_readiness_as_read_only_get() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"][
            "/api/v1/jobs/{job_id}/match-input-readiness"
        ]["get"]

    assert "requestBody" not in operation
    assert "200" in operation["responses"]
    assert "404" in operation["responses"]
