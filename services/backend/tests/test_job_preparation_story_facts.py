"""Tests for deterministic Phase 7 STAR/project story fact selection."""
from __future__ import annotations

from datetime import UTC, datetime

from app.application.career_context.models import EvidenceDetail, ProfileDetail, SkillDetail
from app.application.job_preparation.experience_priority import (
    ExperiencePriorityFacts,
    ExperiencePriorityItem,
)
from app.application.job_preparation.readiness import JobPreparationReadiness
from app.application.job_preparation.story_facts import BuildStoryFactSelectionUseCase
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
                "ev_ui",
                "ui",
                EvidenceType.PROJECT,
                "Built the confirmed React project used by the desktop product.",
                "confirmed",
            ),
            EvidenceDetail(
                "ev_api",
                "api",
                EvidenceType.WORK,
                "Implemented confirmed Python API integration work.",
                "confirmed",
            ),
            EvidenceDetail(
                "ev_unlinked",
                "unlinked",
                EvidenceType.PROJECT,
                "A confirmed project that is not relevant to this job.",
                "confirmed",
            ),
        ),
        skills=(
            SkillDetail("skill_react", "ReactJS", SkillLevel.STRONG, ("ev_ui",)),
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
        requirement_count=2,
        created_at=datetime(2026, 8, 11, tzinfo=UTC),
        requirements=requirements,
    )


def _readiness() -> JobPreparationReadiness:
    return JobPreparationReadiness(
        job_id="job_1",
        preparation_inputs_ready=True,
        profile_id="prof_1",
        profile_version=3,
        extraction_id="extract_1",
        requirement_count=2,
        blockers=(),
    )


def _priority() -> ExperiencePriorityFacts:
    return ExperiencePriorityFacts(
        job_id="job_1",
        facts_usable=True,
        profile_id="prof_1",
        profile_version=3,
        extraction_id="extract_1",
        items=(
            ExperiencePriorityItem(
                evidence_id="ev_ui",
                evidence_type=EvidenceType.PROJECT,
                supporting_requirement_ids=("req_react",),
                matched_capabilities=("React",),
                must_have_count=1,
                requirement_count=1,
            ),
            ExperiencePriorityItem(
                evidence_id="ev_api",
                evidence_type=EvidenceType.WORK,
                supporting_requirement_ids=("req_python",),
                matched_capabilities=("Python",),
                must_have_count=0,
                requirement_count=1,
            ),
        ),
        blockers=(),
    )


def test_story_fact_selection_preserves_only_confirmed_prioritized_facts() -> None:
    result = BuildStoryFactSelectionUseCase().execute(
        readiness=_readiness(),
        profile=_profile(),
        extraction=_extraction(),
        priority=_priority(),
    )

    assert result.facts_usable is True
    assert [item.evidence_id for item in result.items] == ["ev_ui", "ev_api"]
    assert result.items[0].evidence_summary == (
        "Built the confirmed React project used by the desktop product."
    )
    assert result.items[0].supporting_requirement_ids == ("req_react",)
    assert result.items[0].supporting_requirement_texts == ("Need React",)
    assert result.items[0].matched_capabilities == ("React",)
    assert result.items[0].must_have_count == 1
    assert "ev_unlinked" not in [item.evidence_id for item in result.items]
    assert result.db_writes == result.provider_calls == result.trace_runs_created == 0


def test_story_fact_selection_does_not_synthesize_star_fields_or_metrics() -> None:
    result = BuildStoryFactSelectionUseCase().execute(
        readiness=_readiness(),
        profile=_profile(),
        extraction=_extraction(),
        priority=_priority(),
    )

    item = result.items[0]
    assert not hasattr(item, "situation")
    assert not hasattr(item, "task")
    assert not hasattr(item, "action")
    assert not hasattr(item, "result")
    assert not hasattr(item, "metric")
    assert item.evidence_summary == _profile().evidence[0].summary


def test_story_fact_selection_fails_closed_when_priority_identity_is_stale() -> None:
    stale_priority = ExperiencePriorityFacts(
        job_id="job_1",
        facts_usable=True,
        profile_id="prof_1",
        profile_version=2,
        extraction_id="extract_1",
        items=_priority().items,
        blockers=(),
    )

    result = BuildStoryFactSelectionUseCase().execute(
        readiness=_readiness(),
        profile=_profile(),
        extraction=_extraction(),
        priority=stale_priority,
    )

    assert result.facts_usable is False
    assert result.items == ()
    assert result.blockers == ("experience_priority_identity_changed",)
