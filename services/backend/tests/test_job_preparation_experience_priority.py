"""Tests for deterministic Phase 7 project/work evidence prioritization."""
from __future__ import annotations

from datetime import UTC, datetime

from app.application.career_context.models import EvidenceDetail, ProfileDetail, SkillDetail
from app.application.job_preparation.experience_priority import (
    BuildExperiencePriorityUseCase,
)
from app.application.job_preparation.readiness import JobPreparationReadiness
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
            EvidenceDetail("ev_ui", "ui", EvidenceType.PROJECT, "React UI", "confirmed"),
            EvidenceDetail("ev_api", "api", EvidenceType.WORK, "Python API", "confirmed"),
            EvidenceDetail("ev_degree", "degree", EvidenceType.EDUCATION, "Degree", "confirmed"),
        ),
        skills=(
            SkillDetail("skill_react", "ReactJS", SkillLevel.STRONG, ("ev_ui",)),
            SkillDetail("skill_ts", "TypeScript", SkillLevel.STRONG, ("ev_ui",)),
            SkillDetail("skill_python", "Python", SkillLevel.WORKING, ("ev_api",)),
        ),
        created_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def _requirement(
    requirement_id: str,
    capability: str,
    importance: RequirementImportance,
) -> JobRequirementDetail:
    return JobRequirementDetail(
        id=requirement_id,
        job_id="job_1",
        extraction_id="extract_1",
        requirement_index=0,
        type=RequirementType.SKILL,
        original_text=f"Need {capability}",
        normalized_capability=capability,
        importance=importance,
        evidence_span=f"Need {capability}",
        confidence=0.95,
        extractor_version="v1",
    )


def _extraction() -> JobRequirementExtractionDetail:
    requirements = (
        _requirement("req_react", "React", RequirementImportance.MUST_HAVE),
        _requirement("req_ts", "TypeScript", RequirementImportance.PREFERRED),
        _requirement("req_python", "Python", RequirementImportance.PREFERRED),
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
        requirement_count=3,
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
        requirement_count=3 if ready else 0,
        blockers=(),
    )


def test_experience_priority_ranks_only_linked_project_and_work_evidence() -> None:
    result = BuildExperiencePriorityUseCase().execute(
        readiness=_readiness(), profile=_profile(), extraction=_extraction()
    )

    assert result.facts_usable is True
    assert [item.evidence_id for item in result.items] == ["ev_ui", "ev_api"]
    assert result.items[0].supporting_requirement_ids == ("req_react", "req_ts")
    assert result.items[0].matched_capabilities == ("React", "TypeScript")
    assert result.items[0].must_have_count == 1
    assert result.items[0].requirement_count == 2
    assert result.items[1].supporting_requirement_ids == ("req_python",)
    assert result.items[1].must_have_count == 0
    assert result.db_writes == result.provider_calls == result.trace_runs_created == 0


def test_experience_priority_does_not_infer_relevance_from_evidence_text() -> None:
    profile = _profile()
    profile = ProfileDetail(
        id=profile.id,
        version=profile.version,
        headline=profile.headline,
        years_of_experience=profile.years_of_experience,
        evidence=profile.evidence + (
            EvidenceDetail(
                "ev_kafka_text",
                "kafka-text",
                EvidenceType.PROJECT,
                "Built a Kafka streaming demo",
                "confirmed",
            ),
        ),
        skills=profile.skills,
        created_at=profile.created_at,
    )
    extraction = _extraction()

    result = BuildExperiencePriorityUseCase().execute(
        readiness=_readiness(), profile=profile, extraction=extraction
    )

    assert "ev_kafka_text" not in [item.evidence_id for item in result.items]


def test_experience_priority_fails_closed_on_frozen_identity_change() -> None:
    extraction = _extraction()
    stale = JobRequirementExtractionDetail(
        extraction_id="extract_2",
        job_id=extraction.job_id,
        input_hash=extraction.input_hash,
        extractor_version=extraction.extractor_version,
        provider=extraction.provider,
        model=extraction.model,
        prompt_version=extraction.prompt_version,
        trace_run_id=extraction.trace_run_id,
        requirement_count=extraction.requirement_count,
        created_at=extraction.created_at,
        requirements=extraction.requirements,
    )

    result = BuildExperiencePriorityUseCase().execute(
        readiness=_readiness(), profile=_profile(), extraction=stale
    )

    assert result.facts_usable is False
    assert result.items == ()
    assert result.blockers == ("requirement_identity_changed",)
