"""Deterministic capability normalization over released TargetCohort requirements."""
from __future__ import annotations

from dataclasses import replace

from app.application.target_cohort_capability_normalization import (
    NormalizeTargetCohortCapabilitiesUseCase,
)
from app.application.target_cohort_requirement_aggregation import (
    TargetCohortRequirementAggregationResult,
    TargetCohortRequirementBlocker,
    TargetCohortRequirementFact,
)
from app.domain.job_requirements import RequirementImportance, RequirementType


def _fact(
    requirement_id: str,
    *,
    job_id: str,
    capability: str | None,
    requirement_type: RequirementType = RequirementType.SKILL,
    importance: RequirementImportance = RequirementImportance.PREFERRED,
) -> TargetCohortRequirementFact:
    return TargetCohortRequirementFact(
        requirement_id=requirement_id,
        job_id=job_id,
        extraction_id=f"ext_{job_id}",
        requirement_index=0,
        type=requirement_type,
        original_text=f"Need {capability or 'experience'}",
        normalized_capability=capability,
        importance=importance,
        evidence_span=f"Need {capability or 'experience'}",
        confidence=0.95,
        extractor_version="requirement-extractor-v3",
    )


def _aggregation(*facts: TargetCohortRequirementFact) -> TargetCohortRequirementAggregationResult:
    return TargetCohortRequirementAggregationResult(
        cohort_id="cohort_1",
        job_ids=("job_1", "job_2", "job_3"),
        facts_usable=True,
        sources=(),
        requirements=facts,
        blockers=(),
    )


def test_explicit_aliases_collapse_to_one_capability_and_preserve_provenance() -> None:
    result = NormalizeTargetCohortCapabilitiesUseCase().execute(
        _aggregation(
            _fact("req_1", job_id="job_1", capability="React.js", importance=RequirementImportance.MUST_HAVE),
            _fact("req_2", job_id="job_2", capability="ReactJS"),
            _fact("req_3", job_id="job_2", capability="React"),
        )
    )

    assert result.facts_usable is True
    assert len(result.capabilities) == 1
    capability = result.capabilities[0]
    assert capability.capability == "React"
    assert capability.source_capabilities == ("React.js", "ReactJS", "React")
    assert capability.requirement_ids == ("req_1", "req_2", "req_3")
    assert capability.job_ids == ("job_1", "job_2")
    assert capability.requirement_count == 3
    assert capability.job_count == 2
    assert capability.must_have_count == 1
    assert capability.preferred_count == 2
    assert capability.bonus_count == 0


def test_bilingual_labels_for_the_same_explicit_capability_collapse_without_fuzzy_matching() -> None:
    result = NormalizeTargetCohortCapabilitiesUseCase().execute(
        _aggregation(
            _fact("req_1", job_id="job_1", capability="AI Coding工具", importance=RequirementImportance.MUST_HAVE),
            _fact("req_2", job_id="job_2", capability="AI编码工具", importance=RequirementImportance.MUST_HAVE),
        )
    )

    assert len(result.capabilities) == 1
    capability = result.capabilities[0]
    assert capability.capability == "AI Coding Tools"
    assert capability.source_capabilities == ("AI Coding工具", "AI编码工具")
    assert capability.requirement_ids == ("req_1", "req_2")
    assert capability.job_ids == ("job_1", "job_2")
    assert capability.must_have_count == 2


def test_unknown_capability_is_not_fuzzily_merged_and_non_skill_facts_are_ignored() -> None:
    result = NormalizeTargetCohortCapabilitiesUseCase().execute(
        _aggregation(
            _fact("req_1", job_id="job_1", capability="React Native"),
            _fact("req_2", job_id="job_2", capability="React"),
            _fact(
                "req_3",
                job_id="job_3",
                capability=None,
                requirement_type=RequirementType.EXPERIENCE,
            ),
        )
    )

    assert [item.capability for item in result.capabilities] == ["React Native", "React"]
    assert [item.requirement_ids for item in result.capabilities] == [("req_1",), ("req_2",)]


def test_explicit_example_or_alternative_lists_expose_exact_member_options_without_fuzzy_inference() -> None:
    facts = (
        replace(
            _fact("req_1", job_id="job_1", capability="LangChain, RAG, Agent", importance=RequirementImportance.MUST_HAVE),
            original_text="熟悉当前主流AI技术栈,包括但不限于 LangChain、RAG、Agent 等",
        ),
        replace(
            _fact("req_2", job_id="job_2", capability="Dify、Coze"),
            original_text="熟悉Dify、Coze等低代码/无代码AI平台",
        ),
        replace(
            _fact("req_3", job_id="job_3", capability="Shell/Python/Java/Go/TypeScript"),
            original_text="Shell / Python / Java / Go / TypeScript 任意一种基础开发能力",
        ),
        replace(
            _fact("req_4", job_id="job_3", capability="LLM, Prompt Engineering, Fine-tuning, RAG, Agent"),
            original_text="熟悉大语言模型相关技术,有 Prompt Engineering、Fine-tuning、RAG、Agent 等实践经验者优先",
        ),
    )

    result = NormalizeTargetCohortCapabilitiesUseCase().execute(_aggregation(*facts))

    by_name = {item.capability: item for item in result.capabilities}
    assert by_name["LangChain, RAG, Agent"].member_options == ("LangChain", "RAG", "Agent")
    assert by_name["Dify、Coze"].member_options == ("Dify", "Coze")
    assert by_name["Shell/Python/Java/Go/TypeScript"].member_options == (
        "Shell",
        "Python",
        "Java",
        "Go",
        "TypeScript",
    )
    assert by_name["LLM, Prompt Engineering, Fine-tuning, RAG, Agent"].member_options == (
        "LLM",
        "Prompt Engineering",
        "Fine-tuning",
        "RAG",
        "Agent",
    )


def test_plain_conjunctive_compound_does_not_become_an_any_member_option() -> None:
    fact = replace(
        _fact("req_1", job_id="job_1", capability="Python、Java", importance=RequirementImportance.MUST_HAVE),
        original_text="同时熟悉 Python、Java 服务端开发",
    )

    result = NormalizeTargetCohortCapabilitiesUseCase().execute(_aggregation(fact))

    assert result.capabilities[0].member_options == ()


def test_blocked_requirement_aggregation_fails_closed_without_capabilities() -> None:
    blocked = replace(
        _aggregation(_fact("req_1", job_id="job_1", capability="ReactJS")),
        facts_usable=False,
        requirements=(),
        blockers=(TargetCohortRequirementBlocker(job_id="job_1", codes=("release_not_ready",)),),
    )

    result = NormalizeTargetCohortCapabilitiesUseCase().execute(blocked)

    assert result.facts_usable is False
    assert result.capabilities == ()
    assert result.blockers == blocked.blockers
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0
