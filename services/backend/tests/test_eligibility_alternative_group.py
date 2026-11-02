"""「至少满足一项」条件组的整体判定。

回归背景：真实 JD 里出现「背景要求（以下至少满足一项）」，抽取曾把它拆成
三条互相独立的 preferred，于是这道门槛变成「有则加分」，既不会拦住任何人，
也不会提示缺什么。这里固定三条行为：

1. 三项都没有证据时，仍然是一道未决的门（CONDITIONAL），并写明「哪三项」；
2. 命中其中任意一项即视为满足（MATCHED），不需要三项都满足；
3. 「熟悉任一现代框架」这类含「任一」的单个技能要求不得被误当成条件组。
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.application.career_context.models import EvidenceDetail, ProfileDetail, SkillDetail
from app.application.eligibility import RequirementFitStatus
from app.application.eligibility.evaluator import evaluate_eligibility
from app.application.job_requirements.models import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
)
from app.domain.career_context import EvidenceType, SkillLevel
from app.domain.job_requirements import RequirementImportance, RequirementType

NOW = datetime(2026, 11, 2, tzinfo=UTC)

GROUP_TEXT = (
    "背景要求（以下至少满足一项）：\n\n"
    "独立做过面向用户的产品或工具。\n"
    "有产品转技术或技术转产品的经历。\n"
    "独立开发者，或有 AI Side Project、AI 创业经历。"
)


def _profile(*summaries: str) -> ProfileDetail:
    evidence = tuple(
        EvidenceDetail(
            id=f"ev_{index}",
            key=f"k{index}",
            type=EvidenceType.PROJECT,
            summary=summary,
            source="confirmed by user",
        )
        for index, summary in enumerate(summaries)
    )
    return ProfileDetail(
        id="profile_1",
        version=1,
        headline="",
        years_of_experience=8.0,
        evidence=evidence,
        skills=(
            SkillDetail(
                id="skill_ts",
                name="TypeScript",
                level=SkillLevel.STRONG,
                evidence_ids=("ev_0",),
            ),
        ),
        created_at=NOW,
    )


def _requirement(
    index: int,
    text: str,
    *,
    requirement_type: RequirementType = RequirementType.CONSTRAINT,
    importance: RequirementImportance = RequirementImportance.MUST_HAVE,
    capability: str | None = None,
) -> JobRequirementDetail:
    return JobRequirementDetail(
        id=f"req_{index}",
        job_id="job_1",
        extraction_id="reqrun_1",
        requirement_index=index,
        type=requirement_type,
        original_text=text,
        normalized_capability=capability,
        importance=importance,
        evidence_span=text,
        confidence=0.9,
        extractor_version="requirement-extractor-v42.96",
    )


def _extraction(*requirements: JobRequirementDetail) -> JobRequirementExtractionDetail:
    return JobRequirementExtractionDetail(
        extraction_id="reqrun_1",
        job_id="job_1",
        input_hash="abc",
        extractor_version="requirement-extractor-v42.96",
        provider="openai",
        model="qwen3.8-flash",
        prompt_version="requirement-extraction-v1",
        trace_run_id="run_1",
        requirement_count=len(requirements),
        created_at=NOW,
        requirements=requirements,
    )


def _only_result(profile: ProfileDetail, requirement: JobRequirementDetail):
    outcome = evaluate_eligibility(profile=profile, extraction=_extraction(requirement))
    assert len(outcome.requirements) == 1
    return outcome.requirements[0]


def test_alternative_group_without_evidence_stays_an_open_gate() -> None:
    result = _only_result(_profile("负责 React 与 Electron 客户端开发。"), _requirement(0, GROUP_TEXT))

    assert result.status is RequirementFitStatus.CONDITIONAL
    # 必须写明是哪三项都不满足，而不是一句笼统的「背景不足」
    assert "独立做过面向用户的产品或工具" in result.reason
    assert "有产品转技术或技术转产品的经历" in result.reason
    assert "任意一项" in result.reason


def test_alternative_group_matched_by_one_item() -> None:
    profile = _profile("独立开发者，做过面向用户的产品 Side Project，有真实用户。")
    result = _only_result(profile, _requirement(0, GROUP_TEXT))

    assert result.status is RequirementFitStatus.MATCHED
    assert "条件组" in result.reason
    assert result.evidence_ids == ("ev_0",)


def test_alternative_group_is_not_a_skill_gate_by_single_hit() -> None:
    """部分沾边不能算满足，否则「至少满足一项」会被削弱成关键词匹配。"""
    profile = _profile("做过一些工具，但都是内部使用。")
    result = _only_result(profile, _requirement(0, GROUP_TEXT))

    assert result.status is RequirementFitStatus.CONDITIONAL
    assert "部分沾边" in result.reason


def test_any_modern_framework_is_not_an_alternative_group() -> None:
    """「熟悉任一现代框架」是单个技能要求，不能被当成条件组。"""
    profile = _profile("负责 React 与 Electron 客户端开发。")
    requirement = _requirement(
        0,
        "熟悉 TypeScript 与任一现代框架，具备服务端与部署能力。",
        requirement_type=RequirementType.SKILL,
        capability="TypeScript",
    )
    result = _only_result(profile, requirement)

    assert result.status is RequirementFitStatus.MATCHED
    assert "条件组" not in result.reason


def test_single_sentence_with_marker_is_not_a_group() -> None:
    """只有一句话时不是条件组：没有可拆的备选项，交回通用判定。"""
    profile = _profile("负责 React 与 Electron 客户端开发。")
    result = _only_result(profile, _requirement(0, "至少满足一项：能接受出差。"))

    assert "条件组" not in result.reason


def test_group_participates_in_overall_decision() -> None:
    """条件组是 must_have 时，整个岗位判定至少是 CONDITIONAL，不会被算成 ELIGIBLE。"""
    profile = _profile("负责 React 与 Electron 客户端开发。")
    outcome = evaluate_eligibility(profile=profile, extraction=_extraction(_requirement(0, GROUP_TEXT)))

    assert outcome.eligibility.value == "conditional"
    assert outcome.conditional_count == 1


def test_prompt_names_the_chinese_group_markers() -> None:
    """回归：抽取提示词必须点名「至少满足一项」等中文说法。

    遗漏这些说法时，模型会把一个强制条件组拆成几条独立的 preferred，
    门槛就悄悄消失了。这里锁住措辞，避免以后被删掉。
    """
    from app.llm.job_requirement_extractors import _SYSTEM_PROMPT

    for marker in ("至少满足一项", "满足其一", "其中之一", "任意一种", "择一"):
        assert marker in _SYSTEM_PROMPT

    # 「不限/均可」类放宽不能被抽成硬能力，提示词要有明确禁令
    assert "语言不限" in _SYSTEM_PROMPT
    assert "normalizedCapability null" in _SYSTEM_PROMPT

