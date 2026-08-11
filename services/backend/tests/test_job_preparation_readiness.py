"""Tests for the Phase 7 read-only Job Preparation readiness gate."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.career_context.release import CareerContextReleaseReadiness
from app.application.job_preparation.readiness import GetJobPreparationReadinessUseCase
from app.application.job_requirements.release import JobRequirementReleaseReadiness
from app.application.match_inputs.readiness import MatchInputReadiness


@dataclass
class _MatchInputGate:
    result: MatchInputReadiness
    called_with: str | None = None

    def execute(self, job_id: str) -> MatchInputReadiness:
        self.called_with = job_id
        return self.result


def _match_inputs(*, ready: bool) -> MatchInputReadiness:
    now = datetime(2026, 8, 11, tzinfo=UTC)
    career = CareerContextReleaseReadiness(
        release_eligible=ready,
        confirmation_boundary="explicit_versioned_user_confirmation",
        profile_id="prof_1" if ready else None,
        profile_version=1 if ready else None,
        profile_created_at=now if ready else None,
        profile_evidence_count=2 if ready else 0,
        profile_skill_count=1 if ready else 0,
        search_intent_id="intent_1" if ready else None,
        search_intent_version=1 if ready else None,
        search_intent_created_at=now if ready else None,
        search_intent_target_role_count=1 if ready else 0,
        blockers=(),
    )
    requirements = JobRequirementReleaseReadiness(
        job_id="job_1",
        release_eligible=ready,
        current_description_sha256="abc",
        extraction_id="extract_1" if ready else None,
        extraction_input_hash="abc" if ready else None,
        provider="provider" if ready else None,
        model="model" if ready else None,
        extractor_version="v1" if ready else None,
        prompt_version="p1" if ready else None,
        trace_run_id="trace_1" if ready else None,
        requirement_count=2 if ready else 0,
        accepted_baseline_batch_id="batch_1" if ready else None,
        accepted_baseline_decision_id="decision_1" if ready else None,
        accepted_baseline_evidence_fingerprint="fingerprint" if ready else None,
        blockers=(),
    )
    return MatchInputReadiness(
        job_id="job_1",
        inputs_release_eligible=ready,
        career_context=career,
        job_requirements=requirements,
        blockers=(),
    )


def test_job_preparation_readiness_requires_released_profile_and_requirements() -> None:
    gate = _MatchInputGate(_match_inputs(ready=False))

    result = GetJobPreparationReadinessUseCase(match_inputs=gate).execute("job_1")

    assert gate.called_with == "job_1"
    assert result.job_id == "job_1"
    assert result.preparation_inputs_ready is False
    assert result.profile_id is None
    assert result.extraction_id is None
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0


def test_job_preparation_readiness_freezes_fact_identity_when_ready() -> None:
    gate = _MatchInputGate(_match_inputs(ready=True))

    result = GetJobPreparationReadinessUseCase(match_inputs=gate).execute("job_1")

    assert result.preparation_inputs_ready is True
    assert result.profile_id == "prof_1"
    assert result.profile_version == 1
    assert result.extraction_id == "extract_1"
    assert result.requirement_count == 2
    assert result.blockers == ()
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0
