"""Workflow tests for grounded Job Requirement Extraction."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_requirements import (
    InvalidRequirementExtractorOutputError,
    JobDescriptionNotExtractableError,
    JobRequirementExtractionOutput,
    JobRequirementExtractorResult,
    ProposedJobRequirement,
    RequirementExtractorUnavailableError,
)
from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
from app.db.base import Base
from app.db.models import TraceSpanORM
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.llm import DisabledJobRequirementExtractor, FixtureJobRequirementExtractor
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows import ExtractJobRequirementsWorkflow


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'requirements-workflow.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


class PartiallyUngroundedExtractor(AbstractJobRequirementExtractor):
    @property
    def model_name(self) -> str:
        return "partially-ungrounded-requirement-extractor"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        evidence = "具备大型模型训练或推理平台的开发经验"
        return JobRequirementExtractorResult(
            output=JobRequirementExtractionOutput(
                requirements=(
                    ProposedJobRequirement(
                        type=RequirementType.EXPERIENCE,
                        original_text="拥有大模型平台研发经验",
                        normalized_capability=None,
                        importance=RequirementImportance.PREFERRED,
                        evidence_span=evidence,
                        confidence=0.88,
                    ),
                )
            ),
            model=self.model_name,
        )


class WhitespaceNormalizedExtractor(AbstractJobRequirementExtractor):
    @property
    def model_name(self) -> str:
        return "whitespace-normalized-requirement-extractor"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        quote = "熟悉后端系统开发常用组件: MySQL/PostgreSQL、Redis、消息队列(Kafka/RabbitMQ/RocketMQ)"
        return JobRequirementExtractorResult(
            output=JobRequirementExtractionOutput(
                requirements=(
                    ProposedJobRequirement(
                        type=RequirementType.EXPERIENCE,
                        original_text=quote,
                        normalized_capability=None,
                        importance=RequirementImportance.MUST_HAVE,
                        evidence_span=quote,
                        confidence=0.92,
                    ),
                )
            ),
            model=self.model_name,
        )


class WidthNormalizedExtractor(AbstractJobRequirementExtractor):
    @property
    def model_name(self) -> str:
        return "width-normalized-requirement-extractor"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        quote = "对大语言模型（LLM）有深入理解"
        return JobRequirementExtractorResult(
            output=JobRequirementExtractionOutput(
                requirements=(
                    ProposedJobRequirement(
                        type=RequirementType.SKILL,
                        original_text=quote,
                        normalized_capability="LLM",
                        importance=RequirementImportance.MUST_HAVE,
                        evidence_span=quote,
                        confidence=0.95,
                    ),
                )
            ),
            model=self.model_name,
        )


class StaticRequirementExtractor(AbstractJobRequirementExtractor):
    def __init__(self, *requirements: ProposedJobRequirement) -> None:
        self._requirements = requirements

    @property
    def model_name(self) -> str:
        return "static-requirement-extractor"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        return JobRequirementExtractorResult(
            output=JobRequirementExtractionOutput(requirements=self._requirements),
            model=self.model_name,
        )


class HallucinatingExtractor(AbstractJobRequirementExtractor):
    @property
    def model_name(self) -> str:
        return "hallucinating-requirement-extractor"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        return JobRequirementExtractorResult(
            output=JobRequirementExtractionOutput(
                requirements=(
                    ProposedJobRequirement(
                        type=RequirementType.SKILL,
                        original_text="必须掌握 Rust",
                        normalized_capability="Rust",
                        importance=RequirementImportance.MUST_HAVE,
                        evidence_span="必须掌握 Rust",
                        confidence=0.99,
                    ),
                )
            ),
            model=self.model_name,
        )


def _workflow(
    factory: sessionmaker[Session],
    extractor: AbstractJobRequirementExtractor,
) -> ExtractJobRequirementsWorkflow:
    return ExtractJobRequirementsWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(factory),
    )


def test_fixture_workflow_returns_grounded_requirements_and_trace(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "岗位要求：\n"
        "- 熟练掌握 Python 和 FastAPI。\n"
        "- 具备 3 年以上后端开发经验。\n"
        "- 有 Docker 经验者优先。"
    )

    proposal = _workflow(
        session_factory,
        FixtureJobRequirementExtractor(),
    ).execute(job_id="job_fixture", description=description)

    assert proposal.trace_run_id.startswith("run_")
    assert proposal.extractor_version == "requirement-extractor-v11"
    assert proposal.prompt_version == "requirement-extraction-v3"
    assert {item.normalized_capability for item in proposal.requirements} >= {
        "Python",
        "FastAPI",
        "Docker",
    }
    assert all(item.evidence_span in description for item in proposal.requirements)
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert trace.capability == "requirement_extraction"
        assert trace.input_refs["jobId"] == "job_fixture"
        assert "descriptionSha256" in trace.input_refs
        assert description not in str(trace.input_refs)
        assert trace.error is None
        assert trace.output["groundingPolicyVersion"] == "grounding-v1"
        assert trace.output["groundingRepairs"] == []


def test_workflow_repairs_invalid_original_text_from_valid_verbatim_evidence_span(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "具备大型模型训练或推理平台的开发经验"
    description = (
        f"岗位要求：{evidence}，并熟悉工程化交付流程、代码评审、测试和持续集成。"
    )

    proposal = _workflow(session_factory, PartiallyUngroundedExtractor()).execute(
        job_id="job_repairable",
        description=description,
    )

    assert proposal.extractor_version == "requirement-extractor-v11"
    assert proposal.requirements[0].original_text == evidence
    assert proposal.requirements[0].evidence_span == evidence
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert trace.error is None
        assert trace.output["requirements"][0]["originalText"] == evidence
        assert trace.output["groundingRepairs"] == [
            {
                "requirementIndex": 0,
                "field": "originalText",
                "strategy": "verbatim_counterpart",
            }
        ]


def test_workflow_recovers_unique_whitespace_normalized_quote_as_raw_job_slice(
    session_factory: sessionmaker[Session],
) -> None:
    raw_quote = (
        "熟 悉 后 端 系 统 开 发 常 用 组 件 : MySQL/PostgreSQL 、 Redis 、 消 息 队 列\n"
        "(Kafka/RabbitMQ/RocketMQ)"
    )
    description = f"岗位要求：\n{raw_quote}\n并具备分布式系统设计经验。"

    proposal = _workflow(session_factory, WhitespaceNormalizedExtractor()).execute(
        job_id="job_whitespace_repair",
        description=description,
    )

    assert proposal.requirements[0].original_text == raw_quote
    assert proposal.requirements[0].evidence_span == raw_quote
    assert proposal.requirements[0].original_text in description
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert trace.error is None
        assert trace.output["requirements"][0]["originalText"] == raw_quote
        assert trace.output["groundingPolicyVersion"] == "grounding-v1"
        assert trace.output["groundingRepairs"] == [
            {"requirementIndex": 0, "field": "originalText", "strategy": "whitespace"},
            {"requirementIndex": 0, "field": "evidenceSpan", "strategy": "whitespace"},
        ]


def test_workflow_recovers_unique_fullwidth_punctuation_as_raw_job_slice(
    session_factory: sessionmaker[Session],
) -> None:
    raw_quote = "对大语言模型(LLM)有深入理解"
    description = f"模型理解:{raw_quote},熟悉其基本原理、主流模型特点和工程落地方式。"

    proposal = _workflow(session_factory, WidthNormalizedExtractor()).execute(
        job_id="job_width_repair",
        description=description,
    )

    assert proposal.requirements[0].original_text == raw_quote
    assert proposal.requirements[0].evidence_span == raw_quote
    assert proposal.requirements[0].original_text in description
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert trace.error is None
        assert trace.output["groundingRepairs"] == [
            {
                "requirementIndex": 0,
                "field": "originalText",
                "strategy": "punctuation_width",
            },
            {
                "requirementIndex": 0,
                "field": "evidenceSpan",
                "strategy": "punctuation_width",
            },
        ]


def test_workflow_recovers_mixed_format_drift_as_raw_job_slice(
    session_factory: sessionmaker[Session],
) -> None:
    raw_quote = "模型理解 : 对大语言模型(LLM)有深入理解"
    provider_quote = "模型理解：对大语言模型（LLM）有深入理解"
    description = f"任职要求：\n{raw_quote}\n并熟悉主流模型的特点和局限性。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=provider_quote,
            normalized_capability="LLM",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=provider_quote,
            confidence=0.95,
        )
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_mixed_format_repair",
        description=description,
    )

    assert proposal.requirements[0].original_text == raw_quote
    assert proposal.requirements[0].evidence_span == raw_quote
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert trace.output["groundingRepairs"] == [
            {
                "requirementIndex": 0,
                "field": "originalText",
                "strategy": "whitespace_and_punctuation_width",
            },
            {
                "requirementIndex": 0,
                "field": "evidenceSpan",
                "strategy": "whitespace_and_punctuation_width",
            },
        ]


def test_workflow_does_not_repair_ambiguous_whitespace_normalized_quote(
    session_factory: sessionmaker[Session],
) -> None:
    raw_quote = "熟 悉 后 端 系 统 开 发 常 用 组 件 : MySQL/PostgreSQL 、 Redis 、 消 息 队 列\n(Kafka/RabbitMQ/RocketMQ)"
    description = f"岗位要求：\n{raw_quote}\n其他：\n{raw_quote}\n"

    with pytest.raises(InvalidRequirementExtractorOutputError):
        _workflow(session_factory, WhitespaceNormalizedExtractor()).execute(
            job_id="job_whitespace_ambiguous",
            description=description,
        )


def test_workflow_rejects_semantic_rewrite_instead_of_fuzzy_recovery(
    session_factory: sessionmaker[Session],
) -> None:
    description = "岗位要求：精通 Python，能够独立完成后端服务设计、开发、测试和线上问题排查。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟练 Python",
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟练 Python",
            confidence=0.9,
        )
    )

    with pytest.raises(InvalidRequirementExtractorOutputError):
        _workflow(session_factory, extractor).execute(
            job_id="job_semantic_rewrite",
            description=description,
        )


def test_workflow_rejects_case_only_change(
    session_factory: sessionmaker[Session],
) -> None:
    description = "岗位要求：熟练使用 LangChain 构建 Agent 应用，并具备完整的项目落地经验。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟练使用 langchain 构建 Agent 应用",
            normalized_capability="LangChain",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟练使用 langchain 构建 Agent 应用",
            confidence=0.9,
        )
    )

    with pytest.raises(InvalidRequirementExtractorOutputError):
        _workflow(session_factory, extractor).execute(
            job_id="job_case_change",
            description=description,
        )


def test_workflow_rejects_number_word_rewrite(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "岗位要求：具备 3 年以上 AI 应用开发经验，并能够独立负责复杂项目交付、"
        "工程质量治理、测试验证和线上问题排查。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="具备三年以上 AI 应用开发经验",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="具备三年以上 AI 应用开发经验",
            confidence=0.9,
        )
    )

    with pytest.raises(InvalidRequirementExtractorOutputError):
        _workflow(session_factory, extractor).execute(
            job_id="job_number_rewrite",
            description=description,
        )


def test_workflow_rejects_duplicate_requirements_after_format_recovery(
    session_factory: sessionmaker[Session],
) -> None:
    raw_quote = "熟 悉 Python"
    description = (
        f"岗位要求：{raw_quote}，并具备后端服务开发、测试和线上排障经验，"
        "能够独立负责系统设计、接口治理和持续交付。"
    )
    provider_quote = "熟悉 Python"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=provider_quote,
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=provider_quote,
            confidence=0.9,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=raw_quote,
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=raw_quote,
            confidence=0.9,
        ),
    )

    with pytest.raises(InvalidRequirementExtractorOutputError, match="duplicates"):
        _workflow(session_factory, extractor).execute(
            job_id="job_duplicate_after_repair",
            description=description,
        )


def test_workflow_allows_distinct_requirements_to_share_a_section_evidence_span(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "核心平台建设：\n"
        "设计统一的模型服务接口。\n"
        "构建支持工具调用的 Agent 编排系统。\n"
        "持续优化平台性能、稳定性和可观测性。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text="设计统一的模型服务接口",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="核心平台建设",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text="构建支持工具调用的 Agent 编排系统",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="核心平台建设",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_shared_section_evidence",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == [
        "设计统一的模型服务接口",
        "构建支持工具调用的 Agent 编排系统",
    ]


def test_workflow_repairs_explicit_or_siblings_into_one_mandatory_alternative_group(
    session_factory: sessionmaker[Session],
) -> None:
    description = "任职要求：熟悉 Java 或 Go 编程语言，并具备服务端开发、测试、线上排障和持续交付经验。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉 Java 或 Go 编程语言",
            normalized_capability="Java",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟悉 Java 或 Go 编程语言",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉 Java 或 Go 编程语言",
            normalized_capability="Go",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟悉 Java 或 Go 编程语言",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_or_siblings",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE),
        (RequirementType.SKILL, "Java", RequirementImportance.PREFERRED),
        (RequirementType.SKILL, "Go", RequirementImportance.PREFERRED),
    ]
    assert all(
        item.original_text == "熟悉 Java 或 Go 编程语言"
        and item.evidence_span == "熟悉 Java 或 Go 编程语言"
        for item in proposal.requirements
    )


def test_workflow_converts_inline_cardinality_skill_into_mandatory_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：具备 FrameworkA、FrameworkB、FrameworkC 等至少一种智能体框架的项目经验，"
        "并能独立完成服务开发、测试与交付。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="具备 FrameworkA、FrameworkB、FrameworkC 等至少一种智能体框架的项目经验",
            normalized_capability="FrameworkA",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="具备 FrameworkA、FrameworkB、FrameworkC 等至少一种智能体框架的项目经验",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_inline_cardinality",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE),
    ]


def test_workflow_keeps_soft_inline_alternative_as_non_blocking_skill(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "加分项：熟悉 FrameworkA 或 FrameworkB 者优先，并有良好的工程实践和协作能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉 FrameworkA 或 FrameworkB 者优先",
            normalized_capability="FrameworkA",
            importance=RequirementImportance.PREFERRED,
            evidence_span="熟悉 FrameworkA 或 FrameworkB 者优先",
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_soft_inline_alternative",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance) for item in proposal.requirements] == [
        (RequirementType.SKILL, "FrameworkA", RequirementImportance.PREFERRED),
    ]


def test_workflow_does_not_repair_plain_skill_enumeration_as_or_alternative(
    session_factory: sessionmaker[Session],
) -> None:
    description = "任职要求：熟悉 TensorFlow、PyTorch 等主流深度学习框架，并具备模型训练、评估、部署和线上排障经验。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉 TensorFlow、PyTorch 等主流深度学习框架",
            normalized_capability="TensorFlow",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟悉 TensorFlow、PyTorch 等主流深度学习框架",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉 TensorFlow、PyTorch 等主流深度学习框架",
            normalized_capability="PyTorch",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟悉 TensorFlow、PyTorch 等主流深度学习框架",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_plain_enumeration",
        description=description,
    )

    assert [(item.normalized_capability, item.importance) for item in proposal.requirements] == [
        ("TensorFlow", RequirementImportance.MUST_HAVE),
        ("PyTorch", RequirementImportance.MUST_HAVE),
    ]


def test_workflow_softens_a_threshold_when_the_same_clause_explicitly_waives_it(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：\n"
        "1. 3 年以上平台开发经验，表现优秀者可放宽至不限年限。\n"
        "2. 熟练使用 Python，能够独立完成服务开发与测试。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="3 年以上平台开发经验",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="3 年以上平台开发经验",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="表现优秀者可放宽至不限年限",
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span="表现优秀者可放宽至不限年限",
            confidence=0.92,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟练使用 Python",
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟练使用 Python",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_waiver_scope",
        description=description,
    )

    assert proposal.extractor_version == "requirement-extractor-v11"
    assert [(item.original_text, item.importance) for item in proposal.requirements] == [
        (
            "3 年以上平台开发经验，表现优秀者可放宽至不限年限",
            RequirementImportance.PREFERRED,
        ),
        ("熟练使用 Python", RequirementImportance.MUST_HAVE),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert trace.output["semanticPolicyVersion"] == "requirement-semantics-v4"
        assert {item["strategy"] for item in trace.output["semanticRepairs"]} == {
            "waiver_scope",
            "drop_redundant_waiver",
        }


def test_workflow_does_not_soften_a_threshold_when_waiver_targets_another_clause(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：3 年以上平台开发经验，学历要求可放宽；"
        "同时熟练使用 Python 并具备服务开发、测试与线上排障能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="3 年以上平台开发经验",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="3 年以上平台开发经验",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_unrelated_waiver",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.MUST_HAVE
    assert proposal.requirements[0].original_text == "3 年以上平台开发经验"


def test_workflow_softens_a_combined_threshold_when_waiver_is_in_same_requirement(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：4 年以上后端开发经验，特别优秀者可放宽（不限年限）；"
        "熟练使用 Python 并能独立负责服务交付。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="4 年以上后端开发经验，特别优秀者可放宽（不限年限）",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="4 年以上后端开发经验，特别优秀者可放宽（不限年限）",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_combined_waiver",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.PREFERRED
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "waiver_scope"
        ]


def test_workflow_does_not_soften_combined_threshold_when_waiver_names_other_target(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：4 年以上后端开发经验，学历要求可放宽；"
        "熟练使用 Python 并能独立负责服务交付。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="4 年以上后端开发经验，学历要求可放宽",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="4 年以上后端开发经验，学历要求可放宽",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_combined_unrelated_waiver",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.MUST_HAVE


def test_workflow_splits_hard_clause_from_trailing_preferred_clause(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：\n"
        "1. 熟悉消息队列技术栈，有大型项目落地经验者优先。\n"
        "2. 有主导大型平台项目的经验，熟悉金融业务者优先。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉消息队列技术栈，有大型项目落地经验者优先",
            normalized_capability="消息队列技术栈",
            importance=RequirementImportance.PREFERRED,
            evidence_span="熟悉消息队列技术栈，有大型项目落地经验者优先",
            confidence=0.94,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="有主导大型平台项目的经验，熟悉金融业务者优先",
            normalized_capability="大型平台项目经验与金融业务",
            importance=RequirementImportance.PREFERRED,
            evidence_span="有主导大型平台项目的经验，熟悉金融业务者优先",
            confidence=0.93,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_mixed_hard_soft",
        description=description,
    )

    assert [
        (item.type, item.original_text, item.importance, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            "熟悉消息队列技术栈",
            RequirementImportance.MUST_HAVE,
            "消息队列技术栈",
        ),
        (
            RequirementType.EXPERIENCE,
            "有大型项目落地经验者优先",
            RequirementImportance.PREFERRED,
            None,
        ),
        (
            RequirementType.EXPERIENCE,
            "有主导大型平台项目的经验",
            RequirementImportance.MUST_HAVE,
            None,
        ),
        (
            RequirementType.SKILL,
            "熟悉金融业务者优先",
            RequirementImportance.PREFERRED,
            "金融业务",
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]].count(
            "split_trailing_preferred"
        ) == 2


def test_workflow_does_not_split_an_entire_preferred_alternative_group(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：有支付平台经验，或熟悉风控系统者优先；"
        "同时要求熟练使用 Python 并具备服务开发能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="有支付平台经验，或熟悉风控系统者优先",
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span="有支付平台经验，或熟悉风控系统者优先",
            confidence=0.92,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_preferred_alternative_group",
        description=description,
    )

    assert len(proposal.requirements) == 1
    assert proposal.requirements[0].importance is RequirementImportance.PREFERRED
    assert proposal.requirements[0].original_text == "有支付平台经验，或熟悉风控系统者优先"


def test_workflow_downgrades_children_of_a_mandatory_any_one_group(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：\n"
        "3. 至少在以下一个方向非常熟练：\n"
        "【客户端方向】React、TypeScript、复杂交互。\n"
        "【服务端方向】Python、异步模型、测试工程化。\n"
        "4. 熟练使用 AI Agent 工具进行真实软件开发。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="至少在以下一个方向非常熟练",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="至少在以下一个方向非常熟练",
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="【客户端方向】React、TypeScript、复杂交互。",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="【客户端方向】React、TypeScript、复杂交互。",
            confidence=0.93,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="【服务端方向】Python、异步模型、测试工程化。",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="【服务端方向】Python、异步模型、测试工程化。",
            confidence=0.93,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟练使用 AI Agent 工具进行真实软件开发",
            normalized_capability="AI Agent Tools",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟练使用 AI Agent 工具进行真实软件开发",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_any_one_group",
        description=description,
    )

    assert [item.importance for item in proposal.requirements] == [
        RequirementImportance.MUST_HAVE,
        RequirementImportance.PREFERRED,
        RequirementImportance.PREFERRED,
        RequirementImportance.MUST_HAVE,
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("alternative_child") == 2


def test_workflow_keeps_plain_threshold_mandatory_without_explicit_waiver(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：\n"
        "1. 3 年以上平台开发经验，能够独立负责核心服务。\n"
        "2. 熟练使用 Python。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="3 年以上平台开发经验",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="3 年以上平台开发经验",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_plain_threshold",
        description=description,
    )

    assert proposal.requirements[0].original_text == "3 年以上平台开发经验"
    assert proposal.requirements[0].importance is RequirementImportance.MUST_HAVE
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert trace.output["semanticRepairs"] == []


def test_workflow_keeps_independent_hard_items_mandatory_without_alternative_group(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：\n"
        "1. 熟练使用 React 与 TypeScript。\n"
        "2. 熟练使用 Python 与异步编程。\n"
        "3. 能独立完成测试与部署。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟练使用 React 与 TypeScript",
            normalized_capability="React",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟练使用 React 与 TypeScript",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟练使用 Python 与异步编程",
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟练使用 Python 与异步编程",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_independent_hard_items",
        description=description,
    )

    assert [item.importance for item in proposal.requirements] == [
        RequirementImportance.MUST_HAVE,
        RequirementImportance.MUST_HAVE,
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert trace.output["semanticRepairs"] == []


def test_hallucinated_evidence_is_rejected_and_failure_trace_is_saved(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "岗位要求熟练掌握 Python，并能够使用 FastAPI 开发后端服务，"
        "同时需要参与系统设计、接口治理和线上问题排查。"
    )

    with pytest.raises(InvalidRequirementExtractorOutputError) as captured:
        _workflow(session_factory, HallucinatingExtractor()).execute(
            job_id="job_invalid",
            description=description,
        )

    assert captured.value.run_id is not None
    with session_factory() as session:
        trace = session.get(TraceSpanORM, captured.value.run_id)
        assert trace is not None
        assert "does not occur" in trace.error
        assert trace.output["requirements"][0]["normalizedCapability"] == "Rust"


def test_disabled_provider_failure_is_traced(
    session_factory: sessionmaker[Session],
) -> None:
    description = "岗位要求熟练掌握 Python 和 FastAPI，并具备三年以上后端开发经验。"

    with pytest.raises(RequirementExtractorUnavailableError) as captured:
        _workflow(session_factory, DisabledJobRequirementExtractor()).execute(
            job_id="job_disabled",
            description=description,
        )

    with session_factory() as session:
        trace = session.get(TraceSpanORM, captured.value.run_id)
        assert trace is not None
        assert trace.model == "disabled"
        assert trace.error


def test_short_description_is_rejected_before_provider_and_trace(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(JobDescriptionNotExtractableError):
        _workflow(session_factory, FixtureJobRequirementExtractor()).execute(
            job_id="job_short",
            description="熟悉 Python",
        )

    with session_factory() as session:
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 0
