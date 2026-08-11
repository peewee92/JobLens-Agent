"""Tests for the read-only Phase 7 Job Preparation aggregate query."""
from __future__ import annotations

from datetime import UTC, datetime

from app.application.career_context.models import EvidenceDetail, ProfileDetail, SkillDetail
from app.application.job_preparation.bundle import BuildJobPreparationBundleUseCase
from app.application.job_preparation.readiness import JobPreparationReadiness
from app.application.job_requirements.models import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
)
from app.domain.career_context import EvidenceType, SkillLevel
from app.domain.job_requirements import RequirementImportance, RequirementType


class _ReadinessGate:
    def __init__(self, result: JobPreparationReadiness) -> None:
        self.result = result
        self.calls: list[str] = []

    def execute(self, job_id: str) -> JobPreparationReadiness:
        self.calls.append(job_id)
        return self.result


class _Profiles:
    def __init__(self, profile: ProfileDetail | None) -> None:
        self.profile = profile
        self.reads = 0

    def get_current_profile(self) -> ProfileDetail | None:
        self.reads += 1
        return self.profile


class _Requirements:
    def __init__(self, extraction: JobRequirementExtractionDetail | None) -> None:
        self.extraction = extraction
        self.calls: list[tuple[str, str]] = []

    def get_extraction(self, *, job_id: str, extraction_id: str) -> JobRequirementExtractionDetail | None:
        self.calls.append((job_id, extraction_id))
        return self.extraction


def _profile() -> ProfileDetail:
    return ProfileDetail(
        id="prof_1",
        version=3,
        headline="Frontend engineer",
        years_of_experience=8,
        evidence=(
            EvidenceDetail(
                "ev_react",
                "react-project",
                EvidenceType.PROJECT,
                "Built the confirmed React desktop project.",
                "confirmed",
            ),
        ),
        skills=(
            SkillDetail("skill_react", "ReactJS", SkillLevel.STRONG, ("ev_react",)),
            SkillDetail("skill_python", "Python", SkillLevel.WORKING, ()),
        ),
        created_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def _extraction() -> JobRequirementExtractionDetail:
    requirements = (
        JobRequirementDetail(
            id="req_react",
            job_id="job_1",
            extraction_id="extract_1",
            requirement_index=0,
            type=RequirementType.SKILL,
            original_text="Strong React experience is required",
            normalized_capability="React",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="Strong React experience is required",
            confidence=0.95,
            extractor_version="v1",
        ),
        JobRequirementDetail(
            id="req_python",
            job_id="job_1",
            extraction_id="extract_1",
            requirement_index=1,
            type=RequirementType.SKILL,
            original_text="Python is preferred",
            normalized_capability="Python",
            importance=RequirementImportance.PREFERRED,
            evidence_span="Python is preferred",
            confidence=0.95,
            extractor_version="v1",
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


def _ready() -> JobPreparationReadiness:
    return JobPreparationReadiness(
        job_id="job_1",
        preparation_inputs_ready=True,
        profile_id="prof_1",
        profile_version=3,
        extraction_id="extract_1",
        requirement_count=2,
        blockers=(),
    )


def test_job_preparation_bundle_composes_all_five_grounded_outputs() -> None:
    profiles = _Profiles(_profile())
    requirements = _Requirements(_extraction())
    result = BuildJobPreparationBundleUseCase(
        readiness=_ReadinessGate(_ready()),
        profiles=profiles,
        requirements=requirements,
    ).execute("job_1")

    assert result.facts_usable is True
    assert result.profile_id == "prof_1"
    assert result.profile_version == 3
    assert result.extraction_id == "extract_1"
    assert [item.requirement_id for item in result.resume_delta.highlights] == ["req_react"]
    assert [item.evidence_id for item in result.experience_priority.items] == ["ev_react"]
    assert [item.evidence_id for item in result.story_facts.items] == ["ev_react"]
    assert [item.requirement_id for item in result.interview_facts.items] == [
        "req_react",
        "req_python",
    ]
    assert [item.requirement_id for item in result.study_checklist.items] == ["req_python"]
    assert result.blockers == ()
    assert result.db_writes == result.provider_calls == result.trace_runs_created == 0
    assert profiles.reads == 1
    assert requirements.calls == [("job_1", "extract_1")]


def test_job_preparation_bundle_stops_before_fact_reads_when_readiness_is_blocked() -> None:
    blocked = JobPreparationReadiness(
        job_id="job_1",
        preparation_inputs_ready=False,
        profile_id=None,
        profile_version=None,
        extraction_id=None,
        requirement_count=0,
        blockers=(),
    )
    profiles = _Profiles(_profile())
    requirements = _Requirements(_extraction())

    result = BuildJobPreparationBundleUseCase(
        readiness=_ReadinessGate(blocked),
        profiles=profiles,
        requirements=requirements,
    ).execute("job_1")

    assert result.facts_usable is False
    assert result.resume_delta is None
    assert result.experience_priority is None
    assert result.story_facts is None
    assert result.interview_facts is None
    assert result.study_checklist is None
    assert result.blockers == ("preparation_inputs_not_ready",)
    assert profiles.reads == 0
    assert requirements.calls == []
    assert result.db_writes == result.provider_calls == result.trace_runs_created == 0


def test_job_preparation_bundle_fails_closed_when_frozen_sources_disappear() -> None:
    result = BuildJobPreparationBundleUseCase(
        readiness=_ReadinessGate(_ready()),
        profiles=_Profiles(None),
        requirements=_Requirements(_extraction()),
    ).execute("job_1")

    assert result.facts_usable is False
    assert result.blockers == ("profile_not_found",)
    assert result.resume_delta is None
