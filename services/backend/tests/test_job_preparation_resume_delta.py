"""Tests for deterministic Phase 7 Resume Delta facts."""
from __future__ import annotations

from datetime import UTC, datetime

from app.application.career_context.models import EvidenceDetail, ProfileDetail, SkillDetail
from app.application.job_preparation.readiness import JobPreparationReadiness
from app.application.job_preparation.resume_delta import BuildResumeDeltaFactsUseCase
from app.application.job_requirements.models import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
)
from app.domain.career_context import EvidenceType, SkillLevel
from app.domain.job_requirements import RequirementImportance, RequirementType


def _profile() -> ProfileDetail:
    return ProfileDetail(
        id="prof_1",
        version=3,
        headline="Frontend engineer",
        years_of_experience=8,
        evidence=(
            EvidenceDetail(
                id="ev_react",
                key="react-project",
                type=EvidenceType.PROJECT,
                summary="Built a React desktop workflow.",
                source="confirmed_profile",
            ),
        ),
        skills=(
            SkillDetail(
                id="skill_react",
                name="ReactJS",
                level=SkillLevel.STRONG,
                evidence_ids=("ev_react",),
            ),
            SkillDetail(
                id="skill_python",
                name="Python",
                level=SkillLevel.BASIC,
                evidence_ids=(),
            ),
        ),
        created_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def _requirement(
    *,
    requirement_id: str,
    capability: str | None,
    requirement_type: RequirementType = RequirementType.SKILL,
    importance: RequirementImportance = RequirementImportance.MUST_HAVE,
) -> JobRequirementDetail:
    return JobRequirementDetail(
        id=requirement_id,
        job_id="job_1",
        extraction_id="extract_1",
        requirement_index=0,
        type=requirement_type,
        original_text=f"Need {capability or 'ownership'}",
        normalized_capability=capability,
        importance=importance,
        evidence_span=f"Need {capability or 'ownership'}",
        confidence=0.95,
        extractor_version="v1",
    )


def _extraction() -> JobRequirementExtractionDetail:
    requirements = (
        _requirement(requirement_id="req_react", capability="React"),
        _requirement(requirement_id="req_python", capability="Python"),
        _requirement(requirement_id="req_kafka", capability="Kafka"),
        _requirement(
            requirement_id="req_ownership",
            capability=None,
            requirement_type=RequirementType.RESPONSIBILITY,
        ),
    )
    return JobRequirementExtractionDetail(
        extraction_id="extract_1",
        job_id="job_1",
        input_hash="hash",
        extractor_version="v1",
        provider="provider",
        model="model",
        prompt_version="p1",
        trace_run_id="trace_1",
        requirement_count=len(requirements),
        created_at=datetime(2026, 8, 11, tzinfo=UTC),
        requirements=requirements,
    )


def _readiness(*, ready: bool = True) -> JobPreparationReadiness:
    return JobPreparationReadiness(
        job_id="job_1",
        preparation_inputs_ready=ready,
        profile_id="prof_1" if ready else None,
        profile_version=3 if ready else None,
        extraction_id="extract_1" if ready else None,
        requirement_count=4 if ready else 0,
        blockers=(),
    )


def test_resume_delta_facts_separate_evidenced_and_unsupported_skills() -> None:
    result = BuildResumeDeltaFactsUseCase().execute(
        readiness=_readiness(), profile=_profile(), extraction=_extraction()
    )

    assert result.facts_usable is True
    assert [item.requirement_id for item in result.highlights] == ["req_react"]
    assert result.highlights[0].profile_skill_ids == ("skill_react",)
    assert result.highlights[0].evidence_ids == ("ev_react",)
    assert [(item.requirement_id, item.status.value) for item in result.evidence_gaps] == [
        ("req_python", "unevidenced"),
        ("req_kafka", "missing"),
    ]
    assert result.db_writes == result.provider_calls == result.trace_runs_created == 0


def test_resume_delta_facts_fail_closed_when_readiness_is_not_released() -> None:
    result = BuildResumeDeltaFactsUseCase().execute(
        readiness=_readiness(ready=False), profile=_profile(), extraction=_extraction()
    )

    assert result.facts_usable is False
    assert result.highlights == ()
    assert result.evidence_gaps == ()


def test_resume_delta_facts_fail_closed_on_frozen_identity_change() -> None:
    profile = _profile()
    stale_profile = ProfileDetail(
        id=profile.id,
        version=4,
        headline=profile.headline,
        years_of_experience=profile.years_of_experience,
        evidence=profile.evidence,
        skills=profile.skills,
        created_at=profile.created_at,
    )

    result = BuildResumeDeltaFactsUseCase().execute(
        readiness=_readiness(), profile=stale_profile, extraction=_extraction()
    )

    assert result.facts_usable is False
    assert result.blockers == ("profile_identity_changed",)
