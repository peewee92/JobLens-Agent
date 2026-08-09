"""Deterministic Phase 4 Evidence Retrieval tests."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.career_context.models import EvidenceDetail, ProfileDetail, SkillDetail
from app.application.eligibility import RequirementFitStatus
from app.application.eligibility.evaluator import evaluate_eligibility
from app.application.evidence_retrieval import (
    EvidenceRelevanceTier,
    EvidenceRetrievalBasis,
    EvidenceRetrievalInputsNotReadyError,
    RetrieveJobEvidenceUseCase,
    retrieve_candidate_evidence,
)
from app.application.job_requirements.models import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
)
from app.domain.career_context import EvidenceType, SkillLevel
from app.domain.job_requirements import RequirementImportance, RequirementType

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _profile() -> ProfileDetail:
    evidence = (
        EvidenceDetail(
            id="ev_tools",
            key="agent-tools",
            type=EvidenceType.PROJECT,
            summary="设计 Agent 工具调用、Function Calling、工具集成与用户确认流程。",
            source="confirmed by user",
        ),
        EvidenceDetail(
            id="ev_rag",
            key="rag-project",
            type=EvidenceType.PROJECT,
            summary="建设 RAG 知识库与权限感知检索链路。",
            source="confirmed by user",
        ),
        EvidenceDetail(
            id="ev_frontend",
            key="frontend",
            type=EvidenceType.WORK,
            summary="负责 React、TypeScript 与 Electron 客户端开发。",
            source="confirmed by user",
        ),
    )
    return ProfileDetail(
        id="profile_1",
        version=3,
        headline="8 年复杂系统经验，近年聚焦 AI Agent",
        years_of_experience=8,
        evidence=evidence,
        skills=(
            SkillDetail(
                id="skill_function_calling",
                name="Function Calling",
                level=SkillLevel.STRONG,
                evidence_ids=("ev_tools",),
            ),
            SkillDetail(
                id="skill_rag",
                name="RAG",
                level=SkillLevel.STRONG,
                evidence_ids=("ev_rag",),
            ),
        ),
        created_at=NOW,
    )


def _requirement(
    index: int,
    *,
    text: str,
    capability: str | None,
    importance: RequirementImportance = RequirementImportance.MUST_HAVE,
    type: RequirementType = RequirementType.SKILL,
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
        profile_version: int = 3,
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
                "career_context": type(
                    "CareerReadiness",
                    (),
                    {
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


class _Requirements:
    def __init__(self, extraction: JobRequirementExtractionDetail | None) -> None:
        self.extraction = extraction

    def get_latest(self, job_id: str) -> JobRequirementExtractionDetail | None:
        return self.extraction


def test_exact_skill_link_returns_direct_confirmed_evidence() -> None:
    result = retrieve_candidate_evidence(
        profile=_profile(),
        extraction=_extraction(
            _requirement(0, text="熟悉 RAG", capability="RAG")
        ),
    )

    candidates = result.requirements[0].candidates
    assert len(candidates) == 1
    assert candidates[0].evidence_id == "ev_rag"
    assert candidates[0].relevance_tier is EvidenceRelevanceTier.DIRECT
    assert candidates[0].retrieval_basis is EvidenceRetrievalBasis.EXACT_SKILL_LINK


def test_mcp_related_tools_evidence_is_candidate_but_does_not_change_eligibility() -> None:
    profile = _profile()
    extraction = _extraction(
        _requirement(0, text="熟悉 MCP 协议", capability="MCP")
    )

    retrieval = retrieve_candidate_evidence(profile=profile, extraction=extraction)
    candidates = retrieval.requirements[0].candidates
    assert [item.evidence_id for item in candidates] == ["ev_tools"]
    assert candidates[0].relevance_tier is EvidenceRelevanceTier.RELATED
    assert candidates[0].retrieval_basis is EvidenceRetrievalBasis.RELATED_CAPABILITY_HINT
    assert "Function Calling" in candidates[0].matched_terms

    eligibility = evaluate_eligibility(profile=profile, extraction=extraction)
    assert eligibility.requirements[0].status is RequirementFitStatus.MISSING


def test_explicit_capability_text_in_evidence_is_direct_candidate_without_skill_record() -> None:
    profile = _profile()
    profile_without_rag_skill = ProfileDetail(
        id=profile.id,
        version=profile.version,
        headline=profile.headline,
        years_of_experience=profile.years_of_experience,
        evidence=profile.evidence,
        skills=tuple(skill for skill in profile.skills if skill.name != "RAG"),
        created_at=profile.created_at,
    )
    result = retrieve_candidate_evidence(
        profile=profile_without_rag_skill,
        extraction=_extraction(_requirement(0, text="熟悉 RAG", capability="RAG")),
    )

    candidate = result.requirements[0].candidates[0]
    assert candidate.evidence_id == "ev_rag"
    assert candidate.relevance_tier is EvidenceRelevanceTier.DIRECT
    assert candidate.retrieval_basis is EvidenceRetrievalBasis.EXPLICIT_TEXT_OVERLAP


def test_short_ascii_capability_does_not_match_inside_unrelated_english_words() -> None:
    profile = _profile()
    noisy_profile = ProfileDetail(
        id=profile.id,
        version=profile.version,
        headline=profile.headline,
        years_of_experience=profile.years_of_experience,
        evidence=profile.evidence
        + (
            EvidenceDetail(
                id="ev_maintenance",
                key="maintenance",
                type=EvidenceType.WORK,
                summary="Maintaining frontend infrastructure and release pipelines.",
                source="confirmed by user",
            ),
        ),
        skills=profile.skills,
        created_at=profile.created_at,
    )

    result = retrieve_candidate_evidence(
        profile=noisy_profile,
        extraction=_extraction(_requirement(0, text="熟悉 AI", capability="AI")),
    )

    assert result.requirements[0].candidates == ()


def test_unrelated_requirement_returns_no_candidates_and_never_invents_evidence_ids() -> None:
    profile = _profile()
    result = retrieve_candidate_evidence(
        profile=profile,
        extraction=_extraction(
            _requirement(0, text="精通 Java", capability="Java"),
            _requirement(1, text="5 年支付清结算经验", capability=None, type=RequirementType.EXPERIENCE),
        ),
    )

    assert result.candidate_count == 0
    assert all(item.candidates == () for item in result.requirements)
    valid_ids = {item.id for item in profile.evidence}
    returned_ids = {
        candidate.evidence_id
        for item in result.requirements
        for candidate in item.candidates
    }
    assert returned_ids <= valid_ids


def test_retrieval_use_case_is_read_only_and_refuses_unreleased_inputs() -> None:
    profile = _profile()
    extraction = _extraction(_requirement(0, text="熟悉 RAG", capability="RAG"))
    ready = RetrieveJobEvidenceUseCase(
        readiness=_Readiness(True),
        profiles=_Profiles(profile),
        requirements=_Requirements(extraction),
    ).execute("job_1")

    assert ready.candidate_count == 1
    assert ready.db_writes == 0
    assert ready.provider_calls == 0
    assert ready.trace_runs_created == 0

    blocked = RetrieveJobEvidenceUseCase(
        readiness=_Readiness(False),
        profiles=_Profiles(profile),
        requirements=_Requirements(extraction),
    )
    with pytest.raises(EvidenceRetrievalInputsNotReadyError):
        blocked.execute("job_1")


def test_retrieval_fails_closed_if_profile_or_requirement_changes_after_readiness() -> None:
    profile = _profile()
    extraction = _extraction(_requirement(0, text="熟悉 RAG", capability="RAG"))
    stale = RetrieveJobEvidenceUseCase(
        readiness=_Readiness(profile_version=2),
        profiles=_Profiles(profile),
        requirements=_Requirements(extraction),
    )

    with pytest.raises(EvidenceRetrievalInputsNotReadyError, match="changed after readiness"):
        stale.execute("job_1")
