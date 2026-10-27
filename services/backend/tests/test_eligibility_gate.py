"""Deterministic Phase 4 Eligibility Gate tests."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from app.application.career_context.models import SearchIntentDetail
from app.domain.jobs import RemoteStatus

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


def _intent(**overrides):
    values = dict(id="intent_1", version=1, target_roles=(), cities=(), remote_accepted=None,
                  minimum_salary_k=None, seniority=None, employment_types=(),
                  exclude_keywords=(), hard_constraints=(), soft_preferences=(),
                  created_at=datetime(2026, 8, 9, tzinfo=UTC))
    return SearchIntentDetail(**(values | overrides))

def _job(**overrides):
    return SimpleNamespace(**(dict(id="job_1", title="Engineer", company="Example", area="武汉",
        salary_min_k=20, salary_max_k=30, remote_status=RemoteStatus.REJECTED) | overrides))

class _Jobs:
    def __init__(self, job=None):
        self.job = job or _job()
    def get_job(self, job_id):
        return self.job


def _profile(
    *,
    years: float | None = 8.0,
    education_summary: str = "计算机科学与技术，本科。",
) -> ProfileDetail:
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
            summary=education_summary,
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
    def __init__(
        self,
        eligible: bool = True,
        *,
        profile_id: str = "profile_1",
        profile_version: int = 1,
        extraction_id: str = "reqrun_1",
    ) -> None:
        self.eligible = eligible
        self.profile_id = profile_id
        self.profile_version = profile_version
        self.extraction_id = extraction_id

    def execute(self, job_id: str):
        return type(
            "Readiness",
            (),
            {
                "job_id": job_id,
                "inputs_release_eligible": self.eligible,
                "blockers": () if self.eligible else (type("B", (), {"code": "quality_gate"})(),),
                "career_context": type(
                    "CareerReadiness",
                    (),
                    {
                        "search_intent_id": "intent_1",
                        "search_intent_version": 1,
                        "profile_id": self.profile_id,
                        "profile_version": self.profile_version,
                    },
                )(),
                "job_requirements": type(
                    "RequirementReadiness",
                    (),
                    {"extraction_id": self.extraction_id},
                )(),
            },
        )()


class _Profiles:
    def __init__(self, profile: ProfileDetail | None) -> None:
        self.profile = profile

    def get_current_profile(self) -> ProfileDetail | None:
        return self.profile

    def get_current_search_intent(self):
        return _intent()


class _Requirements:
    def __init__(self, extraction: JobRequirementExtractionDetail | None) -> None:
        self.extraction = extraction

    def get_latest(self, job_id: str) -> JobRequirementExtractionDetail | None:
        return self.extraction


def _use_case(profile: ProfileDetail, extraction: JobRequirementExtractionDetail, *, ready: bool = True):
    return EvaluateJobEligibilityUseCase(
        readiness=_Readiness(ready),
        jobs=_Jobs(),
        profiles=_Profiles(profile),
        requirements=_Requirements(extraction),
    )


def test_unknown_must_have_skill_and_specialized_experience_do_not_block() -> None:
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

    assert result.eligibility is EligibilityDecision.CONDITIONAL
    assert [item.status for item in result.requirements] == [
        RequirementFitStatus.CONDITIONAL,
        RequirementFitStatus.CONDITIONAL,
    ]
    assert result.missing_count == 0
    assert result.conditional_count == 2
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
    assert result.requirements[1].status is RequirementFitStatus.CONDITIONAL
    assert result.eligibility is EligibilityDecision.CONDITIONAL


def test_plain_bachelor_evidence_satisfies_plain_bachelor_requirement() -> None:
    result = _use_case(
        _profile(education_summary="本科。"),
        _extraction(
            _requirement(
                0,
                type=RequirementType.EDUCATION,
                text="本科及以上学历",
                importance=RequirementImportance.MUST_HAVE,
            ),
        ),
    ).execute("job_1")

    assert result.eligibility is EligibilityDecision.ELIGIBLE
    assert result.requirements[0].status is RequirementFitStatus.MATCHED
    assert result.requirements[0].evidence_ids == ("ev_edu",)


def test_bachelor_level_alone_does_not_prove_related_major_requirement() -> None:
    result = _use_case(
        _profile(education_summary="本科。"),
        _extraction(
            _requirement(
                0,
                type=RequirementType.EDUCATION,
                text="本科及以上，计算机相关专业",
                importance=RequirementImportance.MUST_HAVE,
            ),
        ),
    ).execute("job_1")

    assert result.eligibility is EligibilityDecision.CONDITIONAL
    assert result.requirements[0].status is RequirementFitStatus.CONDITIONAL
    assert result.requirements[0].evidence_ids == ("ev_edu",)


def test_computer_science_bachelor_evidence_satisfies_related_major_requirement() -> None:
    result = _use_case(
        _profile(education_summary="计算机科学与技术，本科。"),
        _extraction(
            _requirement(
                0,
                type=RequirementType.EDUCATION,
                text="本科及以上，计算机相关专业",
                importance=RequirementImportance.MUST_HAVE,
            ),
        ),
    ).execute("job_1")

    assert result.eligibility is EligibilityDecision.ELIGIBLE
    assert result.requirements[0].status is RequirementFitStatus.MATCHED
    assert result.requirements[0].evidence_ids == ("ev_edu",)


def test_bachelor_level_alone_does_not_prove_named_school_requirement() -> None:
    result = _use_case(
        _profile(education_summary="本科。"),
        _extraction(
            _requirement(
                0,
                type=RequirementType.EDUCATION,
                text="知名高校本科及以上学历",
                importance=RequirementImportance.MUST_HAVE,
            ),
        ),
    ).execute("job_1")

    assert result.eligibility is EligibilityDecision.CONDITIONAL
    assert result.requirements[0].status is RequirementFitStatus.CONDITIONAL
    assert result.requirements[0].evidence_ids == ("ev_edu",)


def test_unstructured_must_have_experience_stays_conditional_for_semantic_match() -> None:
    result = _use_case(
        _profile(),
        _extraction(
            _requirement(
                0,
                type=RequirementType.EXPERIENCE,
                text="有 LLM/Agent 应用落地项目经验",
                importance=RequirementImportance.MUST_HAVE,
            ),
        ),
    ).execute("job_1")

    assert result.eligibility is EligibilityDecision.CONDITIONAL
    assert result.requirements[0].status is RequirementFitStatus.CONDITIONAL
    assert result.missing_count == 0


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


def test_eligibility_fails_closed_if_profile_or_requirement_changes_after_readiness() -> None:
    profile = _profile()
    extraction = _extraction(
        _requirement(
            0,
            type=RequirementType.SKILL,
            text="熟悉 RAG",
            importance=RequirementImportance.MUST_HAVE,
            capability="RAG",
        )
    )
    stale = EvaluateJobEligibilityUseCase(
        readiness=_Readiness(profile_version=99),
        jobs=_Jobs(),
        profiles=_Profiles(profile),
        requirements=_Requirements(extraction),
    )

    with pytest.raises(EligibilityInputsNotReadyError, match="changed after readiness"):
        stale.execute("job_1")


@pytest.mark.parametrize("years, expected", [
    (None, EligibilityDecision.CONDITIONAL),
    (3, EligibilityDecision.BLOCKED),
    (5, EligibilityDecision.ELIGIBLE),
])
def test_confirmed_total_years_can_block_but_unknown_years_cannot(years, expected) -> None:
    result = _use_case(_profile(years=years), _extraction(_requirement(
        0, type=RequirementType.EXPERIENCE, text="5年以上工作经验",
        importance=RequirementImportance.MUST_HAVE,
    ))).execute("job_1")
    assert result.eligibility is expected
    assert result.provider_calls == result.db_writes == 0
    if expected is EligibilityDecision.BLOCKED:
        assert result.requirements[0].profile_fact_refs == ("yearsOfExperience",)
        assert result.requirements[0].status is RequirementFitStatus.MISSING
    elif years is None:
        assert not result.requirements[0].profile_fact_refs


@pytest.mark.parametrize("education", [None, "本科。", "完成课程。"])
def test_missing_higher_degree_proof_does_not_prove_insufficient_education(education) -> None:
    from dataclasses import replace
    profile = _profile(education_summary=education or "")
    if education is None:
        profile = replace(profile, evidence=tuple(
            item for item in profile.evidence if item.type is not EvidenceType.EDUCATION
        ))
    result = _use_case(profile, _extraction(_requirement(
        0, type=RequirementType.EDUCATION, text="硕士及以上学历",
        importance=RequirementImportance.MUST_HAVE,
    ))).execute("job_1")
    assert result.eligibility is EligibilityDecision.CONDITIONAL
    assert result.missing_count == 0
    assert result.requirements[0].evidence_ids == ()
