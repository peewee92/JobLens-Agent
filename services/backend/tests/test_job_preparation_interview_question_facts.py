"""Tests for deterministic Phase 7 interview-question fact candidates."""
from __future__ import annotations

from datetime import UTC, datetime

from app.application.career_context.models import EvidenceDetail, ProfileDetail, SkillDetail
from app.application.job_preparation.interview_question_facts import (
    BuildInterviewQuestionFactsUseCase,
    InterviewEvidenceStatus,
    InterviewPreparationPriority,
)
from app.application.job_preparation.readiness import JobPreparationReadiness
from app.application.job_preparation.resume_delta import (
    ResumeDeltaEvidenceGap,
    ResumeDeltaFacts,
    ResumeDeltaGapStatus,
    ResumeDeltaHighlight,
)
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


def _requirement(
    requirement_id: str,
    requirement_type: RequirementType,
    text: str,
    capability: str | None,
    importance: RequirementImportance,
    index: int,
) -> JobRequirementDetail:
    return JobRequirementDetail(
        id=requirement_id,
        job_id="job_1",
        extraction_id="extract_1",
        requirement_index=index,
        type=requirement_type,
        original_text=text,
        normalized_capability=capability,
        importance=importance,
        evidence_span=text,
        confidence=0.95,
        extractor_version="v1",
    )


def _extraction() -> JobRequirementExtractionDetail:
    requirements = (
        _requirement(
            "req_python",
            RequirementType.SKILL,
            "Python is preferred",
            "Python",
            RequirementImportance.PREFERRED,
            0,
        ),
        _requirement(
            "req_react",
            RequirementType.SKILL,
            "Strong React experience is required",
            "React",
            RequirementImportance.MUST_HAVE,
            1,
        ),
        _requirement(
            "req_lead",
            RequirementType.RESPONSIBILITY,
            "Lead cross-functional delivery",
            None,
            RequirementImportance.MUST_HAVE,
            2,
        ),
        _requirement(
            "req_kafka",
            RequirementType.SKILL,
            "Kafka is a bonus",
            "Kafka",
            RequirementImportance.BONUS,
            3,
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


def _readiness() -> JobPreparationReadiness:
    return JobPreparationReadiness(
        job_id="job_1",
        preparation_inputs_ready=True,
        profile_id="prof_1",
        profile_version=3,
        extraction_id="extract_1",
        requirement_count=4,
        blockers=(),
    )


def _resume_delta() -> ResumeDeltaFacts:
    return ResumeDeltaFacts(
        job_id="job_1",
        facts_usable=True,
        profile_id="prof_1",
        profile_version=3,
        extraction_id="extract_1",
        highlights=(
            ResumeDeltaHighlight(
                requirement_id="req_react",
                capability="React",
                profile_skill_ids=("skill_react",),
                evidence_ids=("ev_react",),
            ),
        ),
        evidence_gaps=(
            ResumeDeltaEvidenceGap(
                requirement_id="req_python",
                capability="Python",
                status=ResumeDeltaGapStatus.UNEVIDENCED,
                profile_skill_ids=("skill_python",),
            ),
            ResumeDeltaEvidenceGap(
                requirement_id="req_kafka",
                capability="Kafka",
                status=ResumeDeltaGapStatus.MISSING,
                profile_skill_ids=(),
            ),
        ),
        blockers=(),
    )


def test_interview_question_facts_prioritize_requirements_and_preserve_evidence() -> None:
    result = BuildInterviewQuestionFactsUseCase().execute(
        readiness=_readiness(),
        profile=_profile(),
        extraction=_extraction(),
        resume_delta=_resume_delta(),
    )

    assert result.facts_usable is True
    assert [item.requirement_id for item in result.items] == [
        "req_react",
        "req_lead",
        "req_python",
        "req_kafka",
    ]
    react = result.items[0]
    assert react.preparation_priority is InterviewPreparationPriority.HIGH
    assert react.evidence_status is InterviewEvidenceStatus.SUPPORTED
    assert react.evidence_ids == ("ev_react",)
    assert react.evidence_summaries == ("Built the confirmed React desktop project.",)

    responsibility = result.items[1]
    assert responsibility.preparation_priority is InterviewPreparationPriority.HIGH
    assert responsibility.evidence_status is InterviewEvidenceStatus.NOT_ASSESSED
    assert responsibility.evidence_ids == ()

    python = result.items[2]
    assert python.preparation_priority is InterviewPreparationPriority.MEDIUM
    assert python.evidence_status is InterviewEvidenceStatus.UNEVIDENCED
    assert python.profile_skill_ids == ("skill_python",)

    kafka = result.items[3]
    assert kafka.preparation_priority is InterviewPreparationPriority.LOW
    assert kafka.evidence_status is InterviewEvidenceStatus.MISSING
    assert result.db_writes == result.provider_calls == result.trace_runs_created == 0


def test_interview_question_facts_do_not_generate_questions_or_answers() -> None:
    result = BuildInterviewQuestionFactsUseCase().execute(
        readiness=_readiness(),
        profile=_profile(),
        extraction=_extraction(),
        resume_delta=_resume_delta(),
    )

    item = result.items[0]
    assert item.requirement_text == "Strong React experience is required"
    assert not hasattr(item, "question")
    assert not hasattr(item, "answer")
    assert not hasattr(item, "sample_answer")
    assert not hasattr(item, "metric")


def test_interview_question_facts_fail_closed_when_resume_delta_identity_is_stale() -> None:
    stale = ResumeDeltaFacts(
        job_id="job_1",
        facts_usable=True,
        profile_id="prof_1",
        profile_version=2,
        extraction_id="extract_1",
        highlights=_resume_delta().highlights,
        evidence_gaps=_resume_delta().evidence_gaps,
        blockers=(),
    )

    result = BuildInterviewQuestionFactsUseCase().execute(
        readiness=_readiness(),
        profile=_profile(),
        extraction=_extraction(),
        resume_delta=stale,
    )

    assert result.facts_usable is False
    assert result.items == ()
    assert result.blockers == ("resume_delta_identity_changed",)
