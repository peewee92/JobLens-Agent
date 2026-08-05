"""Tests for the read-only Match input preflight composition."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.career_context.release import (
    CareerContextReleaseBlocker,
    CareerContextReleaseBlockerCode,
    CareerContextReleaseReadiness,
)
from app.application.job_requirements.release import (
    JobRequirementReleaseBlocker,
    JobRequirementReleaseBlockerCode,
    JobRequirementReleaseReadiness,
)
from app.application.match_inputs.readiness import (
    GetMatchInputReadinessUseCase,
    MatchInputBlockerSource,
)


@dataclass
class _CareerGate:
    result: CareerContextReleaseReadiness

    def execute(self) -> CareerContextReleaseReadiness:
        return self.result


@dataclass
class _RequirementGate:
    result: JobRequirementReleaseReadiness
    called_with: str | None = None

    def execute(self, job_id: str) -> JobRequirementReleaseReadiness:
        self.called_with = job_id
        return self.result


def _career(*, eligible: bool) -> CareerContextReleaseReadiness:
    blockers = () if eligible else (
        CareerContextReleaseBlocker(
            code=CareerContextReleaseBlockerCode.PROFILE_MISSING,
            message="Profile missing",
        ),
    )
    now = datetime(2026, 8, 5, tzinfo=UTC)
    return CareerContextReleaseReadiness(
        release_eligible=eligible,
        confirmation_boundary="explicit_versioned_user_confirmation",
        profile_id="prof_1" if eligible else None,
        profile_version=1 if eligible else None,
        profile_created_at=now if eligible else None,
        profile_evidence_count=2 if eligible else 0,
        profile_skill_count=1 if eligible else 0,
        search_intent_id="intent_1" if eligible else None,
        search_intent_version=1 if eligible else None,
        search_intent_created_at=now if eligible else None,
        search_intent_target_role_count=1 if eligible else 0,
        blockers=blockers,
    )


def _requirements(*, eligible: bool) -> JobRequirementReleaseReadiness:
    blockers = () if eligible else (
        JobRequirementReleaseBlocker(
            code=JobRequirementReleaseBlockerCode.ACCEPTED_BASELINE_MISSING,
            message="Baseline missing",
        ),
    )
    return JobRequirementReleaseReadiness(
        job_id="job_1",
        release_eligible=eligible,
        current_description_sha256="abc",
        extraction_id="reqrun_1" if eligible else None,
        extraction_input_hash="abc" if eligible else None,
        provider="openai" if eligible else None,
        model="model" if eligible else None,
        extractor_version="v1" if eligible else None,
        prompt_version="p1" if eligible else None,
        trace_run_id="run_1" if eligible else None,
        requirement_count=2 if eligible else 0,
        accepted_baseline_batch_id="batch_1" if eligible else None,
        accepted_baseline_decision_id="decision_1" if eligible else None,
        accepted_baseline_evidence_fingerprint="fingerprint" if eligible else None,
        blockers=blockers,
    )


def test_match_input_readiness_requires_both_fact_gates() -> None:
    for career_ok, requirements_ok, expected in (
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ):
        requirement_gate = _RequirementGate(_requirements(eligible=requirements_ok))
        result = GetMatchInputReadinessUseCase(
            career_context=_CareerGate(_career(eligible=career_ok)),
            job_requirements=requirement_gate,
        ).execute("job_1")

        assert result.inputs_release_eligible is expected
        assert result.job_id == "job_1"
        assert requirement_gate.called_with == "job_1"
        assert result.career_context.release_eligible is career_ok
        assert result.job_requirements.release_eligible is requirements_ok
        assert result.db_writes == 0
        assert result.provider_calls == 0
        assert result.trace_runs_created == 0


def test_match_input_readiness_namespaces_all_blockers_without_hiding_evidence() -> None:
    result = GetMatchInputReadinessUseCase(
        career_context=_CareerGate(_career(eligible=False)),
        job_requirements=_RequirementGate(_requirements(eligible=False)),
    ).execute("job_1")

    assert [(item.source, item.code) for item in result.blockers] == [
        (MatchInputBlockerSource.CAREER_CONTEXT, "profile_missing"),
        (MatchInputBlockerSource.JOB_REQUIREMENTS, "accepted_baseline_missing"),
    ]
    assert [item.message for item in result.blockers] == [
        "Profile missing",
        "Baseline missing",
    ]
