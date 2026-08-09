"""Deterministic Phase 4 Eligibility Gate tests."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.career_context.models import EvidenceDetail, ProfileDetail, SkillDetail
from app.application.eligibility import (
    EligibilityDecision,
    EligibilityInputsNotReadyError,
    EvaluateJobEligibilityUseCase,
    RequirementFitStatus,
)
from app.application.job_requirements.models import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
)
from app.application.match_inputs.readiness import MatchInputReadiness
from app.domain.career_context import EvidenceType, SkillLevel
from app.domain.job_requirements import RequirementImportance, RequirementType


NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _profile(*, years: float | None = 8.0) -> ProfileDetail:
    evidence = (
        EvidenceDetail(
            id="ev_agent",
            key="agent-project",
            type=EvidenceType.PROJECT,
            summary="设计企业 AI Agent、RAG 与 Human-in-the-loop 工作流。",
            source="confirmed by user",
        ),
        EvidenceDetail(
            id="ev_frontend",
            key="frontend",
            type=EvidenceType.WORK,
            summary="负责 React、TypeScript 与 Electron 客户端开发。",
            source="confirmed by user",
        ),
        EvidenceDetail(
            id="ev_edu",
            key="education",
            type=EvidenceType.EDUCATION,
            summary="计算机科学与技术，本科。",
            source="confirmed by user",
        ),
    )
    return ProfileDetail(
        id="profile_1",
        version=1,
        headline="8 年复杂系统与前端经验，近年聚焦 AI Agent",
        years_of_experience=years,
        evidence=evidence,
        skills=(
            SkillDetail(
                id="skill_rag",
                name="RAG",
                level=SkillLevel.STRONG,
                evidence_ids=("ev_agent",),
            ),
            SkillDetail(
                id="skill_react",
                name="React",
                level=SkillLevel.STRONG,
                evidence_ids=("ev_frontend",),
            ),
        ),
        created_at=NOW,
    )


def _requirement(
    index: int,
    *,
    type: RequirementType,
    text: str,
    importance: RequirementImportance,
    capability: str | None = None,
) -> JobRequirementDetail:
    return JobRequirementDetail(
        id=f"req_{index}",
        job_id="job_1",
        extraction_id="reqrun_1",
        requirement_index=index,
        type=type,
        original_text=text,
        normalized_capability=capability,
        importance=importance,
        evidence_span=text,
        confidence=0.95,
        extractor_version="requirement-extractor-v4",
    )


def _extraction(*requirements: JobRequirementDetail) -> JobRequirementExtractionDetail:
    return JobRequirementExtractionDetail(
        extraction_id="reqrun_1",
        job_id="job_1",
        input_hash="abc",
        extractor_version="requirement-extractor-v4",
        provider="openai",
        model="deepseek-v4-flash",
        prompt_version="requirement-extraction-v1",
        trace_run_id="run_1",
        requirement_count=len(requirements),
        created_at=NOW,
        requirements=requirements,
    )


class _Readiness:
    def __init__(self, eligible: bool = True) -> None:
        self.eligible = eligible

    def execute(self, job_id: str):
        return type(
            "Readiness",
            (),
            {
                "job_id": job_id,
                "inputs_release_eligible": self.eligible,
                "blockers": () if self.eligible else (type("B", (), {"code": "quality_gate"})(),),
            },
        )()


class _Profiles:
    def __init__(self, profile: ProfileDetail | None) -> None:
        self.profile = profile

    def get_current_profile(self) -> ProfileDetail | None:
        return self.profile


class _Requirements:
    def __init__(self, extraction: JobRequirementExtractionDetail | None) -> None:
        self.extraction = extraction

    def get_latest(self, job_id: str) -> JobRequirementExtractionDetail | None:
        return self.extraction


def _use_case(profile: ProfileDetail, extraction: JobRequirementExtractionDetail, *, ready: bool = True):
    return EvaluateJobEligibilityUseCase(
        readiness=_Readiness(ready),
        profiles=_Profiles(profile),
        requirements=_Requirements(extraction),
    )


def test_missing_must_have_java_and_specialized_backend_experience_block_job() -> None:
    result = _use_case(
        _profile(),
        _extraction(
            _requirement(
                0,
                type=RequirementType.SKILL,
                text="精通 Java",
                importance=RequirementImportance.MUST_HAVE,
                capability="Java",
            ),
            _requirement(
                1,
                type=RequirementType.EXPERIENCE,
                text="5年以上后端系统开发经验",
                importance=RequirementImportance.MUST_HAVE,
            ),
        ),
    ).execute("job_1")

    assert result.eligibility is EligibilityDecision.BLOCKED
    assert [item.status for item in result.requirements] == [
        RequirementFitStatus.MISSING,
        RequirementFitStatus.MISSING,
    ]
    assert result.missing_count == 2
    assert all(item.evidence_ids == () for item in result.requirements)


def test_exact_confirmed_skill_links_real_profile_evidence() -> None:
    result = _use_case(
        _profile(),
        _extraction(
            _requirement(
                0,
                type=RequirementType.SKILL,
                text="熟悉 RAG",
                importance=RequirementImportance.MUST_HAVE,
                capability="RAG",
            ),
            _requirement(
                1,
                type=RequirementType.SKILL,
                text="熟悉 LangChain 者优先",
                importance=RequirementImportance.BONUS,
                capability="LangChain",
            ),
        ),
    ).execute("job_1")

    assert result.eligibility is EligibilityDecision.ELIGIBLE
    assert result.requirements[0].status is RequirementFitStatus.MATCHED
    assert result.requirements[0].evidence_ids == ("ev_agent",)
    assert result.requirements[1].status is RequirementFitStatus.CONDITIONAL
    assert result.matched_count == 1
    assert result.conditional_count == 1


def test_generic_total_experience_can_use_confirmed_profile_years_but_specialized_years_cannot() -> None:
    result = _use_case(
        _profile(years=8),
        _extraction(
            _requirement(
                0,
                type=RequirementType.EXPERIENCE,
                text="5年以上工作经验",
                importance=RequirementImportance.MUST_HAVE,
            ),
            _requirement(
                1,
                type=RequirementType.EXPERIENCE,
                text="3年以上 AI 算法开发经验",
                importance=RequirementImportance.MUST_HAVE,
            ),
        ),
    ).execute("job_1")

    assert result.requirements[0].status is RequirementFitStatus.MATCHED
    assert result.requirements[0].profile_fact_refs == ("yearsOfExperience",)
    assert result.requirements[1].status is RequirementFitStatus.MISSING
    assert result.eligibility is EligibilityDecision.BLOCKED


def test_unstructured_must_have_responsibility_stays_conditional_instead_of_guessing() -> None:
    result = _use_case(
        _profile(),
        _extraction(
            _requirement(
                0,
                type=RequirementType.RESPONSIBILITY,
                text="负责推动 AI 产品在企业办公场景落地",
                importance=RequirementImportance.MUST_HAVE,
            ),
        ),
    ).execute("job_1")

    assert result.eligibility is EligibilityDecision.CONDITIONAL
    assert result.requirements[0].status is RequirementFitStatus.CONDITIONAL


def test_eligibility_refuses_to_run_before_match_inputs_are_released() -> None:
    use_case = _use_case(
        _profile(),
        _extraction(
            _requirement(
                0,
                type=RequirementType.SKILL,
                text="熟悉 RAG",
                importance=RequirementImportance.MUST_HAVE,
                capability="RAG",
            )
        ),
        ready=False,
    )

    with pytest.raises(EligibilityInputsNotReadyError):
        use_case.execute("job_1")
