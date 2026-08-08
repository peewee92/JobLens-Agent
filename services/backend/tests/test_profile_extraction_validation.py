"""Deterministic grounding tests for Profile Extraction output."""
from __future__ import annotations

import pytest

from app.application.profile_extraction import (
    InvalidProfileExtractorOutputError,
    ProfileExtractionOutput,
    ProposedEvidence,
    ProposedSkill,
)
from app.application.profile_extraction.validation import validate_profile_extraction_output
from app.domain.career_context import EvidenceType, SkillLevel


def _output(evidence_span: str) -> ProfileExtractionOutput:
    return ProfileExtractionOutput(
        headline="AI 产品经理",
        years_of_experience=8,
        evidence=(
            ProposedEvidence(
                key="ahoy_design",
                type=EvidenceType.PROJECT,
                summary="主导 AI Agent 协作产品方案设计",
                source="resume",
                evidence_span=evidence_span,
            ),
        ),
        skills=(
            ProposedSkill(
                name="AI Agent",
                level=SkillLevel.STRONG,
                evidence_keys=("ahoy_design",),
            ),
        ),
        warnings=(),
    )


def test_unique_markdown_formatting_difference_is_aligned_to_exact_source_span() -> None:
    resume = (
        "## 项目经历\n"
        "- **主导 AI Agent 协作产品从 0 到 1 方案设计**，定义 Popeye AI Chat、"
        "Chat-to-Task 等核心场景。"
    )
    model_span = (
        "主导 AI Agent 协作产品从 0 到 1 方案设计，定义 Popeye AI Chat、"
        "Chat-to-Task 等核心场景。"
    )

    result = validate_profile_extraction_output(resume, _output(model_span))

    repaired = result.evidence[0].evidence_span
    assert repaired == (
        "**主导 AI Agent 协作产品从 0 到 1 方案设计**，定义 Popeye AI Chat、"
        "Chat-to-Task 等核心场景。"
    )
    assert repaired in resume


def test_unique_whitespace_difference_is_aligned_to_exact_source_span() -> None:
    resume = "项目成果：负责跨团队\n协同交付，并完成上线验证。"

    result = validate_profile_extraction_output(
        resume,
        _output("负责跨团队协同交付，并完成上线验证。"),
    )

    assert result.evidence[0].evidence_span == "负责跨团队\n协同交付，并完成上线验证。"


def test_ambiguous_formatting_alignment_remains_fail_closed() -> None:
    resume = "**AI** Agent 方案落地；另一个项目同样完成 **AI** Agent 方案落地。"

    with pytest.raises(
        InvalidProfileExtractorOutputError,
        match="does not occur",
    ):
        validate_profile_extraction_output(resume, _output("AI Agent 方案落地"))


def test_semantic_rewrite_is_not_treated_as_formatting_alignment() -> None:
    resume = "主导 AI Agent 协作产品方案设计，并完成上线验证。"

    with pytest.raises(
        InvalidProfileExtractorOutputError,
        match="does not occur",
    ):
        validate_profile_extraction_output(
            resume,
            _output("负责 AI Agent 协作产品方案设计，并完成上线验证。"),
        )
