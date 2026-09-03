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
    RequirementExtractorFailedError,
    RequirementExtractorUnavailableError,
)
from app.application.job_requirements.validation import validate_job_requirement_output
from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
from app.db.base import Base
from app.db.models import TraceSpanORM
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.llm import DisabledJobRequirementExtractor, FixtureJobRequirementExtractor
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows import ExtractJobRequirementsWorkflow


def test_final_requirement_limit_remains_fail_closed_above_fifty() -> None:
    description = "\n".join(f"要求项 {index}: 必须满足" for index in range(51))
    output = JobRequirementExtractionOutput(
        requirements=tuple(
            ProposedJobRequirement(
                type=RequirementType.CONSTRAINT,
                original_text=f"要求项 {index}: 必须满足",
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=f"要求项 {index}: 必须满足",
                confidence=0.95,
            )
            for index in range(51)
        )
    )

    with pytest.raises(
        InvalidRequirementExtractorOutputError,
        match="returned more than 50 requirements",
    ):
        validate_job_requirement_output(description, output)


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


class DiagnosticFailureExtractor(AbstractJobRequirementExtractor):
    @property
    def model_name(self) -> str:
        return "diagnostic-failure-requirement-extractor"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        raise RequirementExtractorFailedError(
            "simulated structured output failure",
            failure_stage="structured_output_json",
            input_tokens=123,
            output_tokens=456,
            provider_finish_reason="length",
            output_chars=789,
            requested_max_completion_tokens=456,
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


def test_workflow_records_failed_provider_token_diagnostics_in_trace(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "岗位要求：熟练使用 Python，并具备真实软件项目开发经验与良好工程实践，"
        "能够独立完成服务开发、测试、上线排障与持续交付。"
    )

    with pytest.raises(RequirementExtractorFailedError) as exc_info:
        _workflow(session_factory, DiagnosticFailureExtractor()).execute(
            job_id="job_provider_diagnostics",
            description=description,
        )

    assert exc_info.value.run_id is not None
    with session_factory() as session:
        trace = session.get(TraceSpanORM, exc_info.value.run_id)
        assert trace is not None
        assert trace.input_tokens == 123
        assert trace.output_tokens == 456
        assert trace.error == "simulated structured output failure"


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
    assert proposal.extractor_version == "requirement-extractor-v42.95"
    assert proposal.prompt_version == "requirement-extraction-v7"
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
        assert trace.output["coveragePolicyVersion"] == "requirement-coverage-v4"
        assert trace.output["coverageAudit"]["enforced"] is False


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

    assert proposal.extractor_version == "requirement-extractor-v42.95"
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


def test_workflow_drops_exact_duplicate_requirements_after_format_recovery(
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

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_duplicate_after_repair",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.SKILL, RequirementImportance.MUST_HAVE, raw_quote),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "drop_exact_duplicate_requirement"
        ]


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


def test_workflow_repairs_postfixed_one_of_language_siblings_into_one_mandatory_group(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟练掌握C/C++/Go/Python等一种以上编程语言"
    description = f"任职要求：{original}；并具备良好的系统问题分析能力。"
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=original,
                normalized_capability=capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=original,
                confidence=0.95,
            )
            for capability in ("C", "C++", "Go", "Python")
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_postfixed_one_of_languages",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE),
    ]


def test_workflow_repairs_explicit_or_siblings_with_mixed_importance_into_one_mandatory_group(
    session_factory: sessionmaker[Session],
) -> None:
    original = "精通 Python 或 Go 或 Java 至少一门语言,具备良好的工程规范和代码品味"
    description = f"任职要求：{original}。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Go",
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=0.9,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Java",
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_or_siblings_mixed_importance",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE),
        (RequirementType.SKILL, "Python", RequirementImportance.PREFERRED),
        (RequirementType.SKILL, "Go", RequirementImportance.PREFERRED),
        (RequirementType.SKILL, "Java", RequirementImportance.PREFERRED),
    ]


def test_workflow_does_not_leak_inline_language_cardinality_scope_into_bare_numbered_siblings(
    session_factory: sessionmaker[Session],
) -> None:
    parent = "精通 Python 或 Go 或 Java 至少一门语言,具备良好的工程规范和代码品味"
    backend = "熟悉后端系统开发常用组件: MySQL/PostgreSQL、Redis、消息队列"
    distributed = "具备分布式系统或微服务架构的设计与实战经验"
    docker = "熟练使用 Docker、Kubernetes,理解云原生的核心设计理念"
    description = "\n".join(
        (
            "二、任职要求",
            "3. 编程与工程能力",
            f"1 {parent}",
            f"2 {backend}",
            f"3 {distributed}",
            f"4 {docker}",
            "4. AI 技术能力",
            "1 扎实的机器学习和深度学习理论基础",
        )
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"1 {parent}",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=backend,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"2 {backend}",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=distributed,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"3 {distributed}",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=docker,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"4 {docker}",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_bare_numbered_sibling_scope_boundary",
        description=description,
    )

    assert [item.importance for item in proposal.requirements] == [
        RequirementImportance.MUST_HAVE,
        RequirementImportance.MUST_HAVE,
        RequirementImportance.MUST_HAVE,
        RequirementImportance.MUST_HAVE,
    ]


def test_workflow_converts_single_combined_language_cardinality_skill_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "精通 Python 或 Go 或 Java 至少一门语言,具备良好的工程规范和代码品味"
    description = f"任职要求：{original}。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Python, Go, or Java",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_single_combined_language_cardinality",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE),
    ]


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


def test_workflow_converts_inline_cardinality_experience_into_mandatory_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：具备 FrameworkA、FrameworkB、FrameworkC 等至少一种智能体框架的实际项目经验，"
        "并能独立完成服务开发、测试与交付。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="具备 FrameworkA、FrameworkB、FrameworkC 等至少一种智能体框架的实际项目经验",
            normalized_capability="至少一种智能体框架",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="具备 FrameworkA、FrameworkB、FrameworkC 等至少一种智能体框架的实际项目经验",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_inline_cardinality_experience",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE),
    ]


def test_workflow_normalizes_provider_type_drift_for_mandatory_alternative_group(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：工程能力扎实，至少在以下一个方向非常熟练（会其中一个方向即可）："
        "React、Electron、Python 或工程化。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="工程能力扎实，至少在以下一个方向非常熟练（会其中一个方向即可）",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="工程能力扎实，至少在以下一个方向非常熟练（会其中一个方向即可）",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_mandatory_alternative_type_drift",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            "工程能力扎实，至少在以下一个方向非常熟练（会其中一个方向即可）",
        ),
    ]


def test_workflow_splits_experience_threshold_from_later_alternative_group_without_losing_threshold(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：3年以上平台开发经验，至少在以下一个方向非常熟练，"
        "并能独立完成服务开发、测试与交付。"
    )
    original = "3年以上平台开发经验，至少在以下一个方向非常熟练"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_experience_threshold_then_alternative",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.EXPERIENCE,
            None,
            RequirementImportance.MUST_HAVE,
            "3年以上平台开发经验",
        ),
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            "至少在以下一个方向非常熟练",
        ),
    ]


def test_workflow_splits_experience_prefix_from_cardinality_group(
    session_factory: sessionmaker[Session],
) -> None:
    original = "具备 LLM 应用工程实战经验,至少覆盖以下方向中的 两项:"
    description = (
        f"任职要求：{original}\n"
        "模型微调；RAG 架构设计；Agent 开发；Prompt Engineering。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_experience_prefix_then_cardinality",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.EXPERIENCE,
            None,
            RequirementImportance.MUST_HAVE,
            "具备 LLM 应用工程实战经验",
        ),
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            "至少覆盖以下方向中的 两项:",
        ),
    ]


def test_workflow_splits_experience_prefix_from_cardinality_even_when_provider_calls_it_skill(
    session_factory: sessionmaker[Session],
) -> None:
    original = "具备 LLM 应用工程实战经验,至少覆盖以下方向中的 两项:"
    description = (
        f"任职要求：{original}\n"
        "模型微调；RAG 架构设计；Agent 开发；Prompt Engineering。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="LLM application engineering, SFT, RAG, Agent, Prompt Engineering",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_experience_prefix_type_drift_to_skill",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.EXPERIENCE,
            None,
            RequirementImportance.MUST_HAVE,
            "具备 LLM 应用工程实战经验",
        ),
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            "至少覆盖以下方向中的 两项:",
        ),
    ]


def test_workflow_recovers_noncontiguous_cardinality_parent_without_leaking_scope(
    session_factory: sessionmaker[Session],
) -> None:
    header = "至少覆盖以下方向中的 两项:"
    children = (
        "模型微调(SFT / LoRA / QLoRA)",
        "RAG 架构设计(文本切分策略、召回排序、向量数据库选型)",
        "Agent / 智能体开发(工具调用、多轮规划、多 Agent 协作)",
        "Prompt Engineering 系统化实践(Few-shot、Chain-of-Thought、结构化输出)",
    )
    malformed_parent = f"{header} {' '.join(children)}"
    description = (
        "任职要求：\n"
        f"3 具备 LLM 应用工程实战经验,{header}\n"
        f"\uf06c {children[0]}\n"
        f"\uf06c {children[1]}\n"
        f"\uf06c {children[2]}\n"
        f"\uf06c {children[3]}\n"
        "4 熟练使用 PyTorch 或 TensorFlow\n"
        "5 有向量数据库(Milvus / Weaviate / Pinecone / Qdrant 等)的实际使用经验\n"
        "6 具备良好的工程实践、测试意识与线上排障能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="具备 LLM 应用工程实战经验",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="具备 LLM 应用工程实战经验",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=malformed_parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=malformed_parent,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=child,
                normalized_capability=(
                    "SFT, LoRA, QLoRA"
                    if index == 0
                    else "RAG"
                    if index == 1
                    else "Agent"
                    if index == 2
                    else "Prompt Engineering"
                ),
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=child,
                confidence=0.95,
            )
            for index, child in enumerate(children)
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟练使用 PyTorch 或 TensorFlow",
            normalized_capability="PyTorch, TensorFlow",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟练使用 PyTorch 或 TensorFlow",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="有向量数据库(Milvus / Weaviate / Pinecone / Qdrant 等)的实际使用经验",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="有向量数据库(Milvus / Weaviate / Pinecone / Qdrant 等)的实际使用经验",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_noncontiguous_cardinality_parent",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    assert by_text[header].type is RequirementType.CONSTRAINT
    assert by_text[header].importance is RequirementImportance.MUST_HAVE
    assert all(
        by_text[child].importance is RequirementImportance.PREFERRED
        for child in children
    )
    assert (
        by_text["熟练使用 PyTorch 或 TensorFlow"].importance
        is RequirementImportance.MUST_HAVE
    )
    assert (
        by_text["有向量数据库(Milvus / Weaviate / Pinecone / Qdrant 等)的实际使用经验"].importance
        is RequirementImportance.MUST_HAVE
    )
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert "recover_alternative_group_header" in strategies
        assert strategies.count("alternative_child") == 4


def test_workflow_bounds_line_start_bare_numbered_second_cardinality_group(
    session_factory: sessionmaker[Session],
) -> None:
    parent = (
        "4 熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain / LlamaIndex / Dify 等至少一种"
    )
    sibling = "5 有向量数据库(Milvus / Weaviate / Pinecone / Qdrant 等)的实际使用经验"
    description = (
        "二、任职要求\n"
        "4. AI 技术能力\n"
        f"{parent}\n"
        f"{sibling}\n"
        "三、加分项(满足越多越优先)\n"
        "1. 有 CUDA 编程或模型推理优化经验\n"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=sibling[len("5 ") :],
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=sibling,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4270_second_cardinality_scope",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    assert by_text[parent].importance is RequirementImportance.MUST_HAVE
    vector_requirement = by_text[sibling[len("5 ") :]]
    assert vector_requirement.type is RequirementType.EXPERIENCE
    assert vector_requirement.importance is RequirementImportance.MUST_HAVE
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert "requirement_section_default_must_have" in strategies
        assert "alternative_child" not in strategies


def test_workflow_softens_same_evidence_children_of_second_inline_cardinality_group(
    session_factory: sessionmaker[Session],
) -> None:
    parent = (
        "4 熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain / LlamaIndex / Dify 等至少一种"
    )
    description = f"二、任职要求\n4. AI 技术能力\n{parent}\n"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.99,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=capability,
                normalized_capability=capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=parent,
                confidence=0.99,
            )
            for capability in ("LangChain", "LlamaIndex", "Dify")
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4276_secondary_inline_cardinality_children",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    assert by_text[parent].importance is RequirementImportance.MUST_HAVE
    assert {
        by_text[capability].importance
        for capability in ("LangChain", "LlamaIndex", "Dify")
    } == {RequirementImportance.PREFERRED}
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [
            item["strategy"] for item in trace.output["semanticRepairs"]
        ].count("alternative_child") >= 3


def test_workflow_recovers_same_evidence_inline_alternative_and_example_parents(
    session_factory: sessionmaker[Session],
) -> None:
    language_evidence = (
        "1 精通 Python 或 Go 或 Java 至少一门语言,具备良好的工程规范和代码品味"
    )
    framework_evidence = (
        "4 熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain / LlamaIndex / Dify 等至少一种"
    )
    vector_evidence = (
        "5 有向量数据库(Milvus / Weaviate / Pinecone / Qdrant 等)的实际使用经验"
    )
    description = (
        "二、任职要求\n"
        "3. 编程与工程能力\n"
        f"{language_evidence}\n"
        "4. AI 技术能力\n"
        f"{framework_evidence}\n"
        f"{vector_evidence}\n"
    )
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=capability,
                normalized_capability=capability.replace("精通 ", ""),
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=language_evidence,
                confidence=0.99,
            )
            for capability in ("精通 Python", "Go", "Java")
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="具备良好的工程规范和代码品味",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=language_evidence,
            confidence=0.99,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=capability,
                normalized_capability=capability.replace("熟练使用 ", ""),
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=framework_evidence,
                confidence=0.99,
            )
            for capability in (
                "熟练使用 PyTorch",
                "TensorFlow",
                "LangChain",
                "LlamaIndex",
                "Dify",
            )
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=capability,
                normalized_capability=capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=vector_evidence,
                confidence=0.99,
            )
            for capability in ("Milvus", "Weaviate", "Pinecone", "Qdrant")
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4284_same_evidence_fanout",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    assert by_text["精通 Python 或 Go 或 Java 至少一门语言"].type is RequirementType.CONSTRAINT
    assert by_text["精通 Python 或 Go 或 Java 至少一门语言"].importance is RequirementImportance.MUST_HAVE
    assert by_text["熟练使用 PyTorch 或 TensorFlow"].type is RequirementType.CONSTRAINT
    assert by_text["熟练使用 PyTorch 或 TensorFlow"].importance is RequirementImportance.MUST_HAVE
    assert by_text["熟悉 LangChain / LlamaIndex / Dify 等至少一种"].type is RequirementType.CONSTRAINT
    assert by_text["熟悉 LangChain / LlamaIndex / Dify 等至少一种"].importance is RequirementImportance.MUST_HAVE
    assert {
        by_text[capability].importance
        for capability in (
            "精通 Python",
            "Go",
            "Java",
            "熟练使用 PyTorch",
            "TensorFlow",
            "LangChain",
            "LlamaIndex",
            "Dify",
        )
    } == {RequirementImportance.PREFERRED}
    assert by_text["具备良好的工程规范和代码品味"].importance is RequirementImportance.MUST_HAVE
    vector_parent = by_text[
        "有向量数据库(Milvus / Weaviate / Pinecone / Qdrant 等)的实际使用经验"
    ]
    assert vector_parent.type is RequirementType.EXPERIENCE
    assert vector_parent.importance is RequirementImportance.MUST_HAVE
    assert not {"Milvus", "Weaviate", "Pinecone", "Qdrant"} & set(by_text)
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("recover_same_evidence_inline_alternative_parent") == 3
        assert strategies.count("recover_same_evidence_example_experience_parent") == 1
        assert strategies.count("drop_example_child") == 4


def test_workflow_does_not_recover_same_evidence_parent_without_explicit_alternative_or_experience(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "1 熟悉 MySQL/PostgreSQL、Redis、Kafka"
    example_evidence = "2 熟悉推理引擎(vLLM / TGI / Triton 等)"
    description = f"二、任职要求\n{evidence}\n{example_evidence}\n"
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=capability,
                normalized_capability=capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=evidence,
                confidence=0.99,
            )
            for capability in ("MySQL", "PostgreSQL", "Redis", "Kafka")
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=capability,
                normalized_capability=capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=example_evidence,
                confidence=0.99,
            )
            for capability in ("vLLM", "TGI", "Triton")
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_v4284_same_evidence_guard",
        description=description,
    )

    assert {item.original_text for item in proposal.requirements} == {
        "MySQL",
        "PostgreSQL",
        "Redis",
        "Kafka",
        "vLLM",
        "TGI",
        "Triton",
    }
    assert {item.importance for item in proposal.requirements} == {
        RequirementImportance.MUST_HAVE
    }
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {item["strategy"] for item in trace.output["semanticRepairs"]}
        assert "recover_same_evidence_inline_alternative_parent" not in strategies
        assert "recover_same_evidence_example_experience_parent" not in strategies


def test_workflow_collapses_same_evidence_framework_member_into_explicit_umbrella_parent(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = (
        "2、核心技能:精通 Python,熟练使用 PyTorch/TensorFlow。"
        "精通 LangChain、LlamaIndex 等大模型应用开发框架。"
        "有 DeepSeek、Qwen、Llama 3 等开源大模型的私有化部署、微调实战经验。"
    )
    child = "精通 LangChain"
    parent = "精通 LangChain、LlamaIndex 等大模型应用开发框架。"
    description = f"【任职要求】\n{evidence}\n"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=child,
            normalized_capability="LangChain",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=parent,
            normalized_capability="LlamaIndex",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_case6_framework_member_parent_duplicate",
        description=description,
    )

    assert [(item.type, item.original_text, item.normalized_capability) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, parent, None)
    ]


def test_workflow_keeps_same_evidence_child_in_non_cardinality_second_clause_hard(
    session_factory: sessionmaker[Session],
) -> None:
    parent = "4 熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain 和 LlamaIndex"
    child = "LangChain"
    description = f"二、任职要求\n4. AI 技术能力\n{parent}\n"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.99,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=child,
            normalized_capability=child,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.99,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_v4277_non_cardinality_second_clause_child",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    assert by_text[child].importance is RequirementImportance.MUST_HAVE


def test_workflow_drops_same_evidence_leading_cardinality_subclause_duplicate(
    session_factory: sessionmaker[Session],
) -> None:
    parent = (
        "4 熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain / LlamaIndex / Dify 等至少一种"
    )
    child = "熟练使用 PyTorch 或 TensorFlow"
    description = f"二、任职要求\n4. AI 技术能力\n{parent}\n"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=child,
            normalized_capability="PyTorchTensorFlow",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.99,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.99,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4271_cardinality_leading_duplicate",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, parent),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_leading_cardinality_subclause" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_drops_same_evidence_leading_cardinality_constraint_duplicate(
    session_factory: sessionmaker[Session],
) -> None:
    parent = (
        "4 熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain / LlamaIndex / Dify 等至少一种"
    )
    child = "熟练使用 PyTorch 或 TensorFlow"
    description = f"二、任职要求\n4. AI 技术能力\n{parent}\n"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=child,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.99,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.99,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4275_cardinality_leading_constraint_duplicate",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, parent),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_leading_cardinality_subclause" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_leading_cardinality_constraint_with_different_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    parent = (
        "4 熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain / LlamaIndex / Dify 等至少一种"
    )
    child = "熟练使用 PyTorch 或 TensorFlow"
    description = f"二、任职要求\n{child}\n{parent}\n"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=child,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=child,
            confidence=0.99,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.99,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_v4276_cardinality_leading_constraint_different_evidence",
        description=description,
    )

    assert {item.original_text for item in proposal.requirements} == {child, parent}


def test_workflow_keeps_leading_cardinality_skill_with_different_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    parent = (
        "4 熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain / LlamaIndex / Dify 等至少一种"
    )
    child = "熟练使用 PyTorch 或 TensorFlow"
    description = (
        "二、任职要求\n"
        f"{child}\n"
        f"{parent}\n"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=child,
            normalized_capability="PyTorchTensorFlow",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=child,
            confidence=0.99,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.99,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_v4271_cardinality_leading_different_evidence",
        description=description,
    )

    assert {item.original_text for item in proposal.requirements} == {child, parent}


def test_workflow_recovers_missing_children_from_explicit_alternative_direction_group(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    children = (
        "【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。",
        "【桌面端方向】:Electron、主进程/渲染进程通信、本地文件系统、进程管理、跨平台桌面应用。",
        "【后端方向】:Python、异步/进程模型、工具系统、服务端架构、测试与工程化。",
        "【工程化/代码控制方向】:Git、branch/worktree、diff/patch、merge/rebase、冲突处理、代码变更追踪、rollback/restore、CI/测试流水线。",
    )
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        + "\n".join(children)
        + "\n"
        "4.不要求 React / Electron / Python / 工程化四个方向都精通,"
        "但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。\n"
        "5.熟练使用 AI Agent 工具进行真实软件开发,对 Agent 产品有高强度使用经验。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="工程能力扎实,至少在以下一个方向非常熟练",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=(
                "不要求 React / Electron / Python / 工程化四个方向都精通,"
                "但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。"
            ),
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=(
                "4.不要求 React / Electron / Python / 工程化四个方向都精通,"
                "但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。"
            ),
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="熟练使用 AI Agent 工具进行真实软件开发",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟练使用 AI Agent 工具进行真实软件开发",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="对 Agent 产品有高强度使用经验",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="对 Agent 产品有高强度使用经验",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_missing_alternative_direction_children",
        description=description,
    )

    expected = dict(zip(children, ("React", "Electron", "Python", "Git"), strict=True))
    by_text = {item.original_text: item for item in proposal.requirements}
    for text, capability in expected.items():
        assert by_text[text].type is RequirementType.SKILL
        assert by_text[text].importance is RequirementImportance.PREFERRED
        assert by_text[text].normalized_capability == capability
    assert by_text["工程能力扎实,至少在以下一个方向非常熟练"].importance is RequirementImportance.MUST_HAVE
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("recover_alternative_group_child") == 4


def test_workflow_normalizes_generic_direction_capabilities_on_existing_alternative_children(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    children = (
        ("【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。", "前端", "React"),
        ("【桌面端方向】:Electron、主进程/渲染进程通信、本地文件系统、进程管理、跨平台桌面应用。", "桌面端", "Electron"),
        ("【后端方向】:Python、异步/进程模型、工具系统、服务端架构、测试与工程化。", "后端", "Python"),
        ("【工程化/代码控制方向】:Git、branch/worktree、diff/patch、merge/rebase、冲突处理、代码变更追踪、rollback/restore、CI/测试流水线。", "工程化", "Git"),
    )
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        + "\n".join(raw for raw, _, _ in children)
        + "\n4.不要求 React / Electron / Python / 工程化四个方向都精通,但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可)",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=raw,
                normalized_capability=generic_capability,
                importance=RequirementImportance.PREFERRED,
                evidence_span=raw,
                confidence=0.95,
            )
            for raw, generic_capability, _ in children
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_generic_alternative_direction_capabilities",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    for raw, _, expected_capability in children:
        assert by_text[raw].importance is RequirementImportance.PREFERRED
        assert by_text[raw].normalized_capability == expected_capability
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("normalize_alternative_group_child_capability") == 4


def test_workflow_normalizes_translated_direction_label_capabilities_on_existing_alternative_children(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    children = (
        ("【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。", "Frontend", "React"),
        ("【桌面端方向】:Electron、主进程/渲染进程通信、本地文件系统、进程管理、跨平台桌面应用。", "Desktop", "Electron"),
        ("【后端方向】:Python、异步/进程模型、工具系统、服务端架构、测试与工程化。", "Backend", "Python"),
        ("【工程化/代码控制方向】:Git、branch/worktree、diff/patch、merge/rebase、冲突处理、代码变更追踪、rollback/restore、CI/测试流水线。", "Engineering/Code Control", "Git"),
    )
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        + "\n".join(raw for raw, _, _ in children)
        + "\n4.不要求 React / Electron / Python / 工程化四个方向都精通,但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可)",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=raw,
                normalized_capability=generic_capability,
                importance=RequirementImportance.PREFERRED,
                evidence_span=raw,
                confidence=0.95,
            )
            for raw, generic_capability, _ in children
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_translated_alternative_direction_capabilities",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    for raw, _, expected_capability in children:
        assert by_text[raw].importance is RequirementImportance.PREFERRED
        assert by_text[raw].normalized_capability == expected_capability
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("normalize_alternative_group_child_capability") == 4


def test_workflow_normalizes_v42_29_generic_direction_semantic_labels(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    children = (
        ("【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。", "frontend engineering", "React"),
        ("【桌面端方向】:Electron、主进程/渲染进程通信、本地文件系统、进程管理、跨平台桌面应用。", "desktop application development", "Electron"),
        ("【后端方向】:Python、异步/进程模型、工具系统、服务端架构、测试与工程化。", "backend engineering", "Python"),
        ("【工程化/代码控制方向】:Git、branch/worktree、diff/patch、merge/rebase、冲突处理、代码变更追踪、rollback/restore、CI/测试流水线。", "engineering infrastructure", "Git"),
    )
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        + "\n".join(raw for raw, _, _ in children)
        + "\n4.不要求四个方向都精通,但至少要能独立 owner 一个核心方向。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent_line,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=raw,
                normalized_capability=generic_capability,
                importance=RequirementImportance.PREFERRED,
                evidence_span=raw,
                confidence=0.95,
            )
            for raw, generic_capability, _ in children
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_v42_29_generic_direction_labels",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    for raw, _, expected_capability in children:
        assert by_text[raw].importance is RequirementImportance.PREFERRED
        assert by_text[raw].normalized_capability == expected_capability
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("normalize_alternative_group_child_capability") == 4


def test_workflow_repairs_responsibility_must_have_alternative_direction_children_from_parent_evidence_scope(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    children = (
        ("【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。", "前端方向", "React"),
        ("【桌面端方向】:Electron、主进程/渲染进程通信、本地文件系统、进程管理、跨平台桌面应用。", "桌面端方向", "Electron"),
        ("【后端方向】:Python、异步/进程模型、工具系统、服务端架构、测试与工程化。", "后端方向", "Python"),
        ("【工程化/代码控制方向】:Git、branch/worktree、diff/patch、merge/rebase、冲突处理、代码变更追踪、rollback/restore、CI/测试流水线。", "工程化/代码控制方向", "Git"),
    )
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        + "\n".join(raw for raw, _, _ in children)
        + "\n4.不要求 React / Electron / Python / 工程化四个方向都精通,但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="工程能力扎实",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.RESPONSIBILITY,
                original_text=raw,
                normalized_capability=generic_capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=raw,
                confidence=0.9,
            )
            for raw, generic_capability, _ in children
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4214_alternative_direction_drift",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    for raw, _, expected_capability in children:
        assert by_text[raw].type is RequirementType.SKILL
        assert by_text[raw].importance is RequirementImportance.PREFERRED
        assert by_text[raw].normalized_capability == expected_capability
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("normalize_alternative_group_child_scope") == 4


def test_workflow_recovers_missing_alternative_parent_before_collapsing_hard_direction_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    frontend_line = "【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。"
    backend_line = "【后端方向】:Python、异步/进程模型、工具系统、服务端架构、测试与工程化。"
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        f"{frontend_line}\n"
        f"{backend_line}\n"
        "4.具备良好的工程习惯和测试意识。"
    )
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=original_text,
                normalized_capability=capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=evidence,
                confidence=0.9,
            )
            for original_text, capability, evidence in (
                ("React", "React", frontend_line),
                ("TypeScript", "TypeScript", frontend_line),
                ("状态管理", "状态管理", frontend_line),
                ("Python", "Python", backend_line),
                ("异步/进程模型", "异步/进程模型", backend_line),
            )
        )
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_missing_alternative_parent_hard_fanout",
        description=description,
    )

    parent_items = [
        item
        for item in proposal.requirements
        if item.type is RequirementType.CONSTRAINT
        and "至少在以下一个方向非常熟练" in item.original_text
    ]
    assert len(parent_items) == 1
    assert parent_items[0].importance is RequirementImportance.MUST_HAVE
    frontend_items = [item for item in proposal.requirements if item.evidence_span == frontend_line]
    backend_items = [item for item in proposal.requirements if item.evidence_span == backend_line]
    assert len(frontend_items) == 1
    assert frontend_items[0].type is RequirementType.SKILL
    assert frontend_items[0].importance is RequirementImportance.PREFERRED
    assert frontend_items[0].normalized_capability == "React"
    assert len(backend_items) == 1
    assert backend_items[0].type is RequirementType.SKILL
    assert backend_items[0].importance is RequirementImportance.PREFERRED
    assert backend_items[0].normalized_capability == "Python"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("recover_missing_alternative_group_parent") == 1
        assert strategies.count("alternative_child") >= 5
        assert strategies.count("collapse_alternative_group_child_siblings") >= 5


def test_workflow_does_not_recover_missing_alternative_parent_when_child_evidence_is_incomplete(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    frontend_line = "【前端方向】:React、TypeScript、复杂交互。"
    backend_line = "【后端方向】:Python、异步模型、服务端架构。"
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        f"{frontend_line}\n"
        f"{backend_line}\n"
        "4.具备良好的工程习惯。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="React",
            normalized_capability="React",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=frontend_line,
            confidence=0.9,
        )
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_incomplete_alternative_parent_evidence",
        description=description,
    )

    assert not any(
        item.type is RequirementType.CONSTRAINT
        and "至少在以下一个方向非常熟练" in item.original_text
        for item in proposal.requirements
    )
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert "recover_missing_alternative_group_parent" not in strategies


def test_workflow_collapses_multiple_preferred_capability_siblings_for_one_alternative_direction(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    child_line = "【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。"
    backend_line = "【后端方向】:Python、异步模型、服务端架构。"
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        f"{child_line}\n"
        f"{backend_line}\n"
        "4.具备良好的工程习惯和测试意识。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="工程能力扎实,至少在以下一个方向非常熟练",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=requirement_type,
                original_text=original_text,
                normalized_capability=capability,
                importance=RequirementImportance.PREFERRED,
                evidence_span=child_line,
                confidence=0.9,
            )
            for requirement_type, original_text, capability in (
                (RequirementType.SKILL, "React", "React"),
                (RequirementType.DOMAIN, "TypeScript", None),
                (RequirementType.DOMAIN, "状态管理", None),
                (RequirementType.DOMAIN, "复杂交互", None),
                (RequirementType.DOMAIN, "桌面端 UI 工程", None),
            )
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=backend_line,
            normalized_capability="Python",
            importance=RequirementImportance.PREFERRED,
            evidence_span=backend_line,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_alternative_direction_capability_fanout",
        description=description,
    )

    frontend_items = [
        item for item in proposal.requirements if item.evidence_span == child_line
    ]
    assert len(frontend_items) == 1
    assert frontend_items[0].type is RequirementType.SKILL
    assert frontend_items[0].importance is RequirementImportance.PREFERRED
    assert frontend_items[0].normalized_capability == "React"
    backend_items = [
        item for item in proposal.requirements if item.original_text == backend_line
    ]
    assert len(backend_items) == 1
    assert backend_items[0].normalized_capability == "Python"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("collapse_alternative_group_child_siblings") == 5
        assert strategies.count("drop_exact_duplicate_requirement") >= 4


def test_workflow_collapses_preferred_experience_type_drift_inside_alternative_direction(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    child_line = "【桌面端方向】:Electron、主进程/渲染进程通信、本地文件系统、进程管理、跨平台桌面应用。"
    backend_line = "【后端方向】:Python、异步模型、服务端架构。"
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        f"{child_line}\n"
        f"{backend_line}\n"
        "4.具备良好的工程习惯和测试意识。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent_line,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="Electron",
            normalized_capability="Electron",
            importance=RequirementImportance.PREFERRED,
            evidence_span=child_line,
            confidence=0.9,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.EXPERIENCE,
                original_text=original_text,
                normalized_capability=None,
                importance=RequirementImportance.PREFERRED,
                evidence_span=child_line,
                confidence=0.9,
            )
            for original_text in (
                "主进程/渲染进程通信",
                "本地文件系统",
                "进程管理",
                "跨平台桌面应用",
            )
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=backend_line,
            normalized_capability="Python",
            importance=RequirementImportance.PREFERRED,
            evidence_span=backend_line,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_alternative_direction_experience_type_drift",
        description=description,
    )

    desktop_items = [item for item in proposal.requirements if item.evidence_span == child_line]
    assert len(desktop_items) == 1
    assert desktop_items[0].type is RequirementType.SKILL
    assert desktop_items[0].importance is RequirementImportance.PREFERRED
    assert desktop_items[0].original_text == child_line
    assert desktop_items[0].normalized_capability == "Electron"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("collapse_alternative_group_child_siblings") == 5


def test_workflow_collapses_preferred_constraint_type_drift_inside_alternative_direction(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    child_line = "【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。"
    backend_line = "【后端方向】:Python、异步模型、服务端架构。"
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        f"{child_line}\n"
        f"{backend_line}\n"
        "4.具备良好的工程习惯和测试意识。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent_line,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="React",
            normalized_capability="React",
            importance=RequirementImportance.PREFERRED,
            evidence_span=child_line,
            confidence=0.9,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.CONSTRAINT,
                original_text=original_text,
                normalized_capability=None,
                importance=RequirementImportance.PREFERRED,
                evidence_span=child_line,
                confidence=0.9,
            )
            for original_text in (
                "状态管理",
                "复杂交互",
                "桌面端 UI 工程",
            )
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=backend_line,
            normalized_capability="Python",
            importance=RequirementImportance.PREFERRED,
            evidence_span=backend_line,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_alternative_direction_constraint_type_drift",
        description=description,
    )

    frontend_items = [item for item in proposal.requirements if item.evidence_span == child_line]
    assert len(frontend_items) == 1
    assert frontend_items[0].type is RequirementType.SKILL
    assert frontend_items[0].importance is RequirementImportance.PREFERRED
    assert frontend_items[0].original_text == child_line
    assert frontend_items[0].normalized_capability == "React"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("collapse_alternative_group_child_siblings") == 4


def test_workflow_preserves_must_have_constraint_inside_alternative_direction(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    child_line = "【前端方向】:React、必须具备安全边界意识。"
    hard_child = "必须具备安全边界意识"
    description = f"【任职要求】\n{parent_line}\n{child_line}\n4.具备良好的工程习惯。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent_line,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="React",
            normalized_capability="React",
            importance=RequirementImportance.PREFERRED,
            evidence_span=child_line,
            confidence=0.9,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=hard_child,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=child_line,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_alternative_direction_hard_constraint",
        description=description,
    )

    hard_items = [item for item in proposal.requirements if item.original_text == hard_child]
    assert len(hard_items) == 1
    assert hard_items[0].type is RequirementType.CONSTRAINT
    assert hard_items[0].importance is RequirementImportance.MUST_HAVE
    assert not any(
        item.original_text == child_line and item.normalized_capability == "React"
        for item in proposal.requirements
    )


def test_workflow_preserves_explicit_experience_inside_alternative_direction(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    child_line = "【桌面端方向】:Electron、3年以上桌面端开发经验。"
    description = f"【任职要求】\n{parent_line}\n{child_line}\n4.具备良好的工程习惯。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent_line,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="Electron",
            normalized_capability="Electron",
            importance=RequirementImportance.PREFERRED,
            evidence_span=child_line,
            confidence=0.9,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="3年以上桌面端开发经验",
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=child_line,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_alternative_direction_explicit_experience",
        description=description,
    )

    desktop_items = [item for item in proposal.requirements if item.evidence_span == child_line]
    assert len(desktop_items) == 2
    assert any(item.type is RequirementType.SKILL for item in desktop_items)
    assert any(
        item.type is RequirementType.EXPERIENCE
        and item.original_text == "3年以上桌面端开发经验"
        for item in desktop_items
    )


def test_workflow_collapses_bonus_capability_fanout_for_one_alternative_direction(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    child_line = "【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。"
    backend_line = "【后端方向】:Python、异步模型、服务端架构。"
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        f"{child_line}\n"
        f"{backend_line}\n"
        "4.具备良好的工程习惯和测试意识。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent_line,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=capability,
                normalized_capability=capability,
                importance=RequirementImportance.BONUS,
                evidence_span=child_line,
                confidence=0.9,
            )
            for capability in ("React", "TypeScript", "状态管理")
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=backend_line,
            normalized_capability="Python",
            importance=RequirementImportance.PREFERRED,
            evidence_span=backend_line,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_alternative_direction_bonus_fanout",
        description=description,
    )

    frontend_items = [item for item in proposal.requirements if item.evidence_span == child_line]
    assert len(frontend_items) == 1
    assert frontend_items[0].type is RequirementType.SKILL
    assert frontend_items[0].importance is RequirementImportance.PREFERRED
    assert frontend_items[0].normalized_capability == "React"


def test_workflow_collapses_full_line_capability_fanout_for_one_alternative_direction(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    child_line = "【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。"
    backend_line = "【后端方向】:Python、异步模型、服务端架构。"
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        f"{child_line}\n"
        f"{backend_line}\n"
        "4.具备良好的工程习惯和测试意识。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent_line,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=child_line,
                normalized_capability=capability,
                importance=RequirementImportance.PREFERRED,
                evidence_span=child_line,
                confidence=0.9,
            )
            for capability in (
                "React",
                "TypeScript",
                "state management",
                "complex interaction",
                "desktop UI engineering",
            )
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=backend_line,
            normalized_capability="Python",
            importance=RequirementImportance.PREFERRED,
            evidence_span=backend_line,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_alternative_direction_full_line_fanout",
        description=description,
    )

    frontend_items = [item for item in proposal.requirements if item.evidence_span == child_line]
    assert len(frontend_items) == 1
    assert frontend_items[0].type is RequirementType.SKILL
    assert frontend_items[0].importance is RequirementImportance.PREFERRED
    assert frontend_items[0].original_text == child_line
    assert frontend_items[0].normalized_capability == "React"
    backend_items = [item for item in proposal.requirements if item.evidence_span == backend_line]
    assert len(backend_items) == 1
    assert backend_items[0].normalized_capability == "Python"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("collapse_alternative_group_child_siblings") == 4
        assert strategies.count("drop_exact_duplicate_requirement") >= 4


def test_workflow_recovers_full_labeled_alternative_direction_from_body_only_child(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    full_line = "【工程化/代码控制方向】:Git、branch/worktree、diff/patch、merge/rebase、冲突处理、代码变更追踪、rollback/restore、CI/测试流水线。"
    body = "Git、branch/worktree、diff/patch、merge/rebase、冲突处理、代码变更追踪、rollback/restore、CI/测试流水线"
    backend_line = "【后端方向】:Python、异步/进程模型、工具系统、服务端架构、测试与工程化。"
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        f"{full_line}\n"
        f"{backend_line}\n"
        "4.不要求四个方向都精通,但至少要能独立 owner 一个核心方向。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent_line,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=body,
            normalized_capability="Git",
            importance=RequirementImportance.PREFERRED,
            evidence_span=full_line,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=backend_line,
            normalized_capability="Python",
            importance=RequirementImportance.PREFERRED,
            evidence_span=backend_line,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4261_alternative_direction_body_only_child",
        description=description,
    )

    engineering_items = [
        item for item in proposal.requirements if item.evidence_span == full_line
    ]
    assert len(engineering_items) == 1
    assert engineering_items[0].original_text == full_line
    assert engineering_items[0].normalized_capability == "Git"
    assert engineering_items[0].importance is RequirementImportance.PREFERRED


def test_workflow_collapses_terminal_punctuation_drifted_full_line_capability_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    child_line = "【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。"
    provider_line = child_line.rstrip("。")
    backend_line = "【后端方向】:Python、异步模型、服务端架构。"
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        f"{child_line}\n"
        f"{backend_line}\n"
        "4.具备良好的工程习惯和测试意识。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent_line,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=provider_line,
                normalized_capability=capability,
                importance=RequirementImportance.PREFERRED,
                evidence_span=child_line,
                confidence=0.9,
            )
            for capability in (
                "React",
                "TypeScript",
                "StateManagement",
                "ComplexInteraction",
                "DesktopUIEngineering",
            )
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=backend_line,
            normalized_capability="Python",
            importance=RequirementImportance.PREFERRED,
            evidence_span=backend_line,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_alternative_direction_full_line_terminal_punctuation_drift",
        description=description,
    )

    frontend_items = [item for item in proposal.requirements if item.evidence_span == child_line]
    assert len(frontend_items) == 1
    assert frontend_items[0].type is RequirementType.SKILL
    assert frontend_items[0].importance is RequirementImportance.PREFERRED
    assert frontend_items[0].original_text == child_line
    assert frontend_items[0].normalized_capability == "React"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("collapse_alternative_group_child_siblings") == 5
        assert strategies.count("drop_exact_duplicate_requirement") >= 4


def test_workflow_preserves_single_terminal_punctuation_drifted_full_line_child(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    child_line = "【前端方向】:React、TypeScript、状态管理。"
    provider_line = child_line.rstrip("。")
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        f"{child_line}\n"
        "【后端方向】:Python、异步模型。\n"
        "4.具备良好的工程习惯。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent_line,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=provider_line,
            normalized_capability="TypeScript",
            importance=RequirementImportance.PREFERRED,
            evidence_span=child_line,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_single_full_line_terminal_punctuation_drift",
        description=description,
    )

    matching = [item for item in proposal.requirements if item.evidence_span == child_line]
    assert len(matching) == 1
    assert matching[0].original_text == provider_line
    assert matching[0].normalized_capability == "TypeScript"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "collapse_alternative_group_child_siblings" not in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_preserves_specific_capability_on_existing_alternative_child(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    child_line = "【前端方向】:React、TypeScript、状态管理、复杂交互。"
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        f"{child_line}\n"
        "【后端方向】:Python、异步模型、服务端架构。\n"
        "4.具备良好的工程习惯和测试意识。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="工程能力扎实,至少在以下一个方向非常熟练",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=child_line,
            normalized_capability="TypeScript",
            importance=RequirementImportance.PREFERRED,
            evidence_span=child_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="【后端方向】:Python、异步模型、服务端架构。",
            normalized_capability="Python",
            importance=RequirementImportance.PREFERRED,
            evidence_span="【后端方向】:Python、异步模型、服务端架构。",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_specific_alternative_direction_capability",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    assert by_text[child_line].normalized_capability == "TypeScript"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert "normalize_alternative_group_child_capability" not in strategies


def test_workflow_does_not_recover_alternative_children_from_mixed_narrative_scope(
    session_factory: sessionmaker[Session],
) -> None:
    parent_line = "3.工程能力扎实,至少在以下一个方向非常熟练:"
    description = (
        "【任职要求】\n"
        f"{parent_line}\n"
        "【前端方向】:React、TypeScript、复杂交互。\n"
        "以上方向会根据团队安排动态调整。\n"
        "【后端方向】:Python、异步模型、服务端架构。\n"
        "4.具备良好的工程习惯和测试意识。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="工程能力扎实,至少在以下一个方向非常熟练",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="具备良好的工程习惯和测试意识。",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="4.具备良好的工程习惯和测试意识。",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_mixed_alternative_child_scope",
        description=description,
    )

    texts = {item.original_text for item in proposal.requirements}
    assert "React、TypeScript、复杂交互。" not in texts
    assert "Python、异步模型、服务端架构。" not in texts
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert "recover_alternative_group_child" not in strategies


def test_workflow_drops_exact_duplicates_after_semantic_normalization(
    session_factory: sessionmaker[Session],
) -> None:
    original = "理解RAG、向量数据库、Function Calling等核心技术,能独立完成原型验证与方案评估"
    description = f"任职要求：{original}。同时具备良好的工程实践、测试意识与协作能力。"
    duplicate = ProposedJobRequirement(
        type=RequirementType.SKILL,
        original_text=original,
        normalized_capability="RAG",
        importance=RequirementImportance.MUST_HAVE,
        evidence_span=original,
        confidence=0.95,
    )
    extractor = StaticRequirementExtractor(duplicate, duplicate, duplicate)

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_exact_provider_duplicates",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("compound_hard_skill_constraint") == 3
        assert strategies.count("drop_exact_duplicate_requirement") == 2


def test_workflow_does_not_hide_conflicting_duplicate_importance(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟练使用 Python"
    description = (
        f"任职要求：{original}，并能独立完成服务开发、测试、发布与线上排障，"
        "同时负责接口治理、持续交付、工程质量和故障复盘。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Python",
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=0.85,
        ),
    )

    with pytest.raises(InvalidRequirementExtractorOutputError, match="duplicates an earlier requirement"):
        _workflow(session_factory, extractor).execute(
            job_id="job_conflicting_duplicate_importance",
            description=description,
        )


def test_workflow_converts_compound_hard_skill_clauses_into_mandatory_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉Prompt工程,能独立设计结构化Prompt,具备上下文管理与复杂意图拆解能力"
    description = f"任职要求：{original};"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Prompt工程",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_compound_hard_skill_clauses",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]


def test_workflow_converts_evaluative_ability_plus_action_into_mandatory_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "优秀的跨部门沟通与业务理解能力,能快速定位痛点并设计技术方案"
    description = f"任职要求：{original}。同时需要良好的工程实践、测试意识与线上问题排查能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="跨部门沟通与业务理解能力",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_evaluative_ability_plus_action",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]


def test_workflow_converts_numbered_compound_hard_skill_clauses_into_mandatory_constraints(
    session_factory: sessionmaker[Session],
) -> None:
    first = "2.精通AI常见场景(如预测、决策、NLP、CV等),具备企业级AI系统架构设计能力。"
    second = "4.优秀的跨部门沟通与业务理解能力,能快速定位痛点并设计技术方案。"
    description = f"任职要求：\n{first}\n{second}\n5.有成功主导千万级以上AI项目的经验。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=first,
            normalized_capability="AI常见场景",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=first,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=second,
            normalized_capability="跨部门沟通与业务理解能力",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=second,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_numbered_compound_hard_skill_clauses",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, first),
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, second),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "compound_hard_skill_constraint",
            "compound_hard_skill_constraint",
        ]


def test_workflow_expands_truncated_compound_hard_skill_from_exact_evidence_span(
    session_factory: sessionmaker[Session],
) -> None:
    prefix = "优秀的跨部门沟通与业务理解能力"
    full = f"{prefix},能快速定位痛点并设计技术方案"
    evidence = f"4.{full}。"
    description = (
        "任职要求：\n"
        f"{evidence}\n"
        "5.有成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径者优先。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=prefix,
            normalized_capability="跨部门沟通与业务理解",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_truncated_compound_hard_evidence",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, full),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "expand_compound_hard_evidence_span"
        ]


def test_workflow_does_not_expand_truncated_skill_when_evidence_suffix_is_soft(
    session_factory: sessionmaker[Session],
) -> None:
    prefix = "熟悉车企数字化转型路径"
    evidence = f"5.{prefix},有相关行业经验者优先。"
    description = f"任职要求：{evidence} 同时需要工程交付、测试验证和线上排障能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=prefix,
            normalized_capability="车企数字化转型路径",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_soft_evidence_suffix_not_expanded",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.SKILL, prefix),
    ]


def test_workflow_splits_hard_tool_usage_from_fused_product_experience(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟练使用 AI Agent 工具进行真实软件开发,对 Agent 产品有高强度使用经验"
    description = f"任职要求：{original}。同时需要良好的工程实践、测试意识与线上问题排查能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_fused_tool_usage_product_experience",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            "熟练使用 AI Agent 工具进行真实软件开发",
        ),
        (
            RequirementType.EXPERIENCE,
            None,
            RequirementImportance.MUST_HAVE,
            "对 Agent 产品有高强度使用经验",
        ),
    ]


def test_workflow_splits_hard_tool_usage_from_fused_product_experience_when_provider_calls_it_skill(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟练使用 AI Agent 工具进行真实软件开发,对 Agent 产品有高强度使用经验。"
    description = (
        f"任职要求：5.{original}\n"
        "6.理解 LLM / Agent 的基本机制并能完成工具调用、上下文管理和测试验证。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Agent Tools",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_fused_tool_usage_skill_type_drift",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance, item.original_text) for item in proposal.requirements] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            "熟练使用 AI Agent 工具进行真实软件开发",
        ),
        (
            RequirementType.EXPERIENCE,
            None,
            RequirementImportance.MUST_HAVE,
            "对 Agent 产品有高强度使用经验",
        ),
    ]


def test_workflow_normalizes_umbrella_conceptual_mechanism_skill_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = (
        "理解 LLM / Agent 的基本机制,包括 LLM API、context window、agent loop、"
        "tool use、reasoning、planning、MCP、memory、subagent 等。"
    )
    evidence = f"6.{original}"
    description = (
        "【任职要求】\n"
        f"{evidence}\n"
        "7.有良好的工程习惯,重视可维护性、测试、可观测性、安全边界和长期演进成本。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="LLM / Agent Mechanisms",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_umbrella_conceptual_mechanism_skill",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "conceptual_mechanism_skill_constraint" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_umbrella_conceptual_mechanism_domain_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = (
        "理解 LLM / Agent 的基本机制,包括 LLM API、context window、agent loop、"
        "tool use、reasoning、planning、MCP、memory、subagent 等。"
    )
    evidence = f"6.{original}"
    description = (
        "【任职要求】\n"
        f"{evidence}\n"
        "7.有良好的工程习惯,重视可维护性、测试、可观测性、安全边界和长期演进成本。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=original,
            normalized_capability="LLM / Agent",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4257_umbrella_conceptual_mechanism_domain",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "conceptual_mechanism_type_constraint" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_umbrella_conceptual_mechanism_domain_without_capability_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = (
        "理解 LLM / Agent 的基本机制,包括 LLM API、context window、agent loop、"
        "tool use、reasoning、planning、MCP、memory、subagent 等。"
    )
    evidence = f"6.{original}"
    description = (
        "【任职要求】\n"
        f"{evidence}\n"
        "7.有良好的工程习惯,重视可维护性、测试、可观测性、安全边界和长期演进成本。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4260_umbrella_conceptual_mechanism_domain_without_capability",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "conceptual_mechanism_type_constraint" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_concrete_mechanism_skill_without_umbrella_concept_list(
    session_factory: sessionmaker[Session],
) -> None:
    original = "理解 Python GIL 的工作机制并能定位并发性能问题"
    description = (
        f"任职要求：{original}，同时熟练使用 Python 并具备服务开发、测试和线上排障经验。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Python GIL",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_concrete_mechanism_skill",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.SKILL, "Python GIL", RequirementImportance.MUST_HAVE, original),
    ]


@pytest.mark.parametrize("normalized_capability", [None, "", "   "])
def test_workflow_normalizes_responsibility_type_drift_for_mandatory_alternative_group(
    session_factory: sessionmaker[Session],
    normalized_capability: str | None,
) -> None:
    original = "工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可)"
    description = (
        f"任职要求：\n3.{original}:\n"
        "【前端方向】:React、TypeScript、复杂交互。\n"
        "【后端方向】:Python、工具系统、服务端架构。\n"
        "4.有良好的工程习惯,重视测试、可观测性和长期演进成本。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=original,
            normalized_capability=normalized_capability,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_responsibility_alternative_type_drift",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]


def test_workflow_converts_explicit_core_technology_list_into_mandatory_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "理解RAG、向量数据库、Function Calling等核心技术"
    description = f"任职要求：{original};并具备良好的工程实践、测试与线上排障能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="RAG",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_core_technology_all_of",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]


def test_workflow_normalizes_explicit_experience_fact_when_provider_calls_it_skill(
    session_factory: sessionmaker[Session],
) -> None:
    original = "需要有车端经验"
    description = (
        f"任职要求：{original}，非车端经验无法满足当前岗位层级；"
        "同时需要参与AI应用设计、测试、交付与线上问题排查。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="车端经验",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_explicit_experience_skill_type_drift",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.EXPERIENCE, None, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "normalize_experience_type_drift"
        ]


def test_workflow_normalizes_explicit_experience_with_followup_qualification_when_provider_calls_it_skill(
    session_factory: sessionmaker[Session],
) -> None:
    originals = [
        "有实际的AI系统集成和部署经验,了解生产环境中AI应用的性能优化和稳定性保障",
        "有实际的模型微调经验,了解不同微调策略的适用场景和效果评估方法",
    ]
    description = "任职要求:\n" + "\n".join(f"{index}.{text}。" for index, text in enumerate(originals, 1))
    extractor = StaticRequirementExtractor(
        *[
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=text,
                normalized_capability="AI capability",
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=f"{index}.{text}。",
                confidence=1.0,
            )
            for index, text in enumerate(originals, 1)
        ],
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4278_experience_followup_type_drift",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.EXPERIENCE, None, RequirementImportance.MUST_HAVE, text)
        for text in originals
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "normalize_experience_type_drift",
            "normalize_experience_type_drift",
        ]


def test_workflow_does_not_convert_skill_first_compound_with_trailing_experience(
    session_factory: sessionmaker[Session],
) -> None:
    original = "了解计算机视觉、自然语言处理、语音识别等多模态AI技术,有跨模态应用开发经验"
    description = f"任职要求：{original}。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Multimodal AI",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_skill_first_compound_trailing_experience",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.original_text) for item in proposal.requirements] == [
        (RequirementType.SKILL, "Multimodal AI", original),
    ]


def test_workflow_extracts_repeated_explicit_experience_prefix_from_explanatory_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "需要有车端经验,非车端经验的无法到副总师的层级"
    description = (
        f"任职要求：{original}；"
        f"岗位补充说明再次强调：{original}；"
        "同时需要负责AI应用设计、验证、交付和线上问题排查。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_explicit_experience_explanatory_constraint",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance, item.original_text) for item in proposal.requirements] == [
        (
            RequirementType.EXPERIENCE,
            None,
            RequirementImportance.MUST_HAVE,
            "需要有车端经验",
        ),
    ]


def test_workflow_trims_explanatory_suffix_from_provider_native_experience(
    session_factory: sessionmaker[Session],
) -> None:
    original = "需要有车端经验,非车端经验的无法到副总师的层级"
    description = f"任职要求：{original}；同时需要负责AI应用设计、验证和交付。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability="车端经验",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_provider_native_experience_with_explanation",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.EXPERIENCE,
            None,
            RequirementImportance.MUST_HAVE,
            "需要有车端经验",
        ),
    ]


def test_workflow_promotes_provider_softened_explicit_mandatory_experience(
    session_factory: sessionmaker[Session],
) -> None:
    original = "需要有车端经验,非车端经验的无法到副总师的层级"
    description = f"岗位补充说明：{original}；同时需要负责AI应用设计、验证和交付。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability="车端经验",
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4277_explicit_vehicle_experience_softened",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.EXPERIENCE,
            None,
            RequirementImportance.MUST_HAVE,
            "需要有车端经验",
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {item["strategy"] for item in trace.output["semanticRepairs"]}
        assert "promote_explicit_mandatory_experience" in strategies
        assert "normalize_experience_type_drift" in strategies


def test_workflow_does_not_promote_soft_marked_experience_preference(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有车端项目经验者优先"
    description = f"岗位补充说明：{original}；同时需要负责AI应用设计、验证和交付，并参与测试、上线复盘和跨团队协作。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability="车端项目经验",
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_soft_vehicle_experience_preference",
        description=description,
    )

    assert [(item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementImportance.PREFERRED, original),
    ]


def test_workflow_keeps_explicit_experience_prefix_when_suffix_is_another_hard_requirement(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有 Agent 项目经验,熟悉 Python 服务开发"
    description = (
        f"任职要求：{original}；"
        "同时需要具备测试、持续交付、可观测性和线上问题排查能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_experience_prefix_plus_independent_hard_requirement",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, original),
    ]


def test_workflow_converts_abstract_engineering_habit_skill_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有良好的工程习惯"
    description = (
        f"任职要求：{original}，重视可维护性、测试、可观测性、安全边界和长期演进成本，"
        "并能够独立完成服务交付与线上故障复盘。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Engineering Habits",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_abstract_engineering_habit",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]


def test_workflow_converts_full_engineering_habit_skill_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有良好的工程习惯,重视可维护性、测试、可观测性、安全边界和长期演进成本。"
    description = f"任职要求：\\n7.{original}\\n8.能够独立完成服务交付与线上故障复盘。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Engineering Habits",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_full_engineering_habit_skill",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "abstract_evaluative_skill_constraint"
        ]


def test_workflow_converts_compound_evaluative_ability_skill_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "具有较强的沟通、表达、总结及文档制作能力,具有高度的责任心,并具有较高的抗压能力。"
    description = f"岗位要求\n7. {original}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="沟通、表达、总结及文档制作能力",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_compound_evaluative_ability_skill",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "abstract_evaluative_skill_constraint" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_converts_split_compound_evaluative_ability_skill_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "7. 具有较强的沟通、表达、总结及文档制作能力,具有高度的责任心,并具有较高的抗压能力。"
    original = "具有较强的沟通、表达、总结及文档制作能力"
    description = f"岗位要求:\n{evidence}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="沟通表达",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.9,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="具有高度的责任心",
            normalized_capability="责任心",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_split_compound_evaluative_ability_skill",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
        (
            RequirementType.CONSTRAINT,
            "责任心",
            RequirementImportance.MUST_HAVE,
            "具有高度的责任心",
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "abstract_evaluative_skill_constraint" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_collapses_engineering_habit_quality_fanout_into_one_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "7.有良好的工程习惯,重视可维护性、测试、可观测性、安全边界和长期演进成本。"
    description = f"任职要求\n{evidence}\n8.能够独立完成服务交付与线上故障复盘。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="重视可维护性",
            normalized_capability="可维护性",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.96,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="测试",
            normalized_capability="测试",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="可观测性",
            normalized_capability="可观测性",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.94,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="安全边界",
            normalized_capability="安全边界",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.93,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="长期演进成本",
            normalized_capability="长期演进成本",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.92,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_engineering_habit_quality_fanout",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            "有良好的工程习惯,重视可维护性、测试、可观测性、安全边界和长期演进成本",
        )
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]].count(
            "collapse_engineering_habit_quality_fanout"
        ) == 5


def test_workflow_preserves_same_evidence_technical_hard_siblings(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "7.熟悉Python、Docker、Kubernetes,并具备服务测试和线上排障能力。"
    description = f"任职要求\n{evidence}\n8.本科及以上学历。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="Python",
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="Docker",
            normalized_capability="Docker",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.94,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="Kubernetes",
            normalized_capability="Kubernetes",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.93,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_same_evidence_technical_hard_siblings",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == [
        "Python",
        "Docker",
        "Kubernetes",
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "collapse_engineering_habit_quality_fanout" not in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_numbered_engineering_habit_responsibility_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "7.有良好的工程习惯,重视可维护性、测试、可观测性、安全边界和长期演进成本。"
    description = f"任职要求：\n{original}\n8.能够独立完成服务交付与线上故障复盘。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_numbered_engineering_habit_responsibility",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "abstract_evaluative_type_constraint"
        ]


def test_workflow_recovers_engineering_habit_constraint_from_source_candidate_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    original = "重视可维护性、测试、可观测性、安全边界和长期演进成本"
    evidence = f"7.有良好的工程习惯,{original}。"
    description = f"任职要求：\n{evidence}\n8.能够独立完成服务交付与线上故障复盘。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_engineering_habit_source_candidate_evidence",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, evidence),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "abstract_evaluative_type_constraint"
        ]


def test_workflow_normalizes_engineering_habit_domain_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有良好的工程习惯"
    evidence = "7.有良好的工程习惯,重视可维护性、测试、可观测性、安全边界和长期演进成本。"
    description = f"任职要求：\n{evidence}\n8.能够独立完成服务交付与线上故障复盘。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=original,
            normalized_capability="Engineering habits",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_engineering_habit_domain",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "abstract_evaluative_type_constraint"
        ]


def test_workflow_keeps_concrete_domain_without_capability_as_domain(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉汽车制造业务领域"
    description = (
        f"任职要求：{original}，并具备企业级项目交付经验，"
        "能够参与需求分析、方案评审、上线验证和跨部门协作。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_concrete_domain_without_capability",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.original_text) for item in proposal.requirements] == [
        (RequirementType.DOMAIN, None, original),
    ]


def test_workflow_keeps_concrete_domain_requirement_as_domain(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉汽车制造业务领域"
    description = (
        f"任职要求：{original}，并具备企业级项目交付经验，"
        "能够参与需求分析、方案评审、上线验证和跨部门协作。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=original,
            normalized_capability="Automotive manufacturing domain",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_concrete_domain_requirement",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.DOMAIN,
            "Automotive manufacturing domain",
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]


def test_workflow_drops_standalone_example_child_when_exact_hard_parent_shares_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "2.精通AI常见场景(如预测、决策、NLP、CV等),具备企业级AI系统架构设计能力。"
    description = f"任职要求：\n{evidence}\n3.具备良好的工程实践、测试意识与持续交付能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="精通AI常见场景",
            normalized_capability="AI常见场景",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="具备企业级AI系统架构设计能力",
            normalized_capability="企业级AI系统架构设计",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text="如预测、决策、NLP、CV等",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_example_child_with_parent",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == [
        "精通AI常见场景",
        "具备企业级AI系统架构设计能力",
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "drop_example_child"
        ]


def test_workflow_drops_inline_parenthetical_example_children_when_hard_umbrella_shares_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "3.熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等),有落地项目经验者优先。"
    description = f"任职要求：\n{evidence}\n4.优秀的跨部门沟通与业务理解能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="LangChain",
            normalized_capability="LangChain",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="AutoGPT",
            normalized_capability="AutoGPT",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)",
            normalized_capability="智能体(Agent)技术栈",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="有落地项目经验者优先",
            normalized_capability="智能体落地项目经验",
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4266_parenthetical_example_children",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            RequirementImportance.MUST_HAVE,
            "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)",
            "智能体(Agent)技术栈",
        ),
        (
            RequirementType.EXPERIENCE,
            RequirementImportance.PREFERRED,
            "有落地项目经验者优先",
            "智能体落地项目经验",
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert strategies.count("drop_example_child") == 2


def test_workflow_keeps_inline_parenthetical_example_child_without_same_evidence_parent(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "3.熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等),有落地项目经验者优先。"
    description = f"任职要求：\n{evidence}\n4.优秀的跨部门沟通与业务理解能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="LangChain",
            normalized_capability="LangChain",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_inline_parenthetical_example_child_without_parent",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == ["LangChain"]


def test_workflow_drops_including_but_not_limited_to_example_fragments_when_hard_parent_shares_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "•对RAG和agent框架有基本了解,包括但不限于 langChain、llama index、autoGen、metaGPT等。"
    description = f"任职要求\n{evidence}\n•熟悉Python语言。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="对RAG和agent框架有基本了解",
            normalized_capability="Retrieval-Augmented Generation",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="包括但不限于 langChain",
            normalized_capability="LangChain",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="llama index",
            normalized_capability="LlamaIndex",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.94,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="autoGen",
            normalized_capability="AutoGen",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.93,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="metaGPT",
            normalized_capability="MetaGPT",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.92,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4246_including_but_not_limited_to_examples",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            RequirementImportance.MUST_HAVE,
            "对RAG和agent框架有基本了解",
        )
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]].count(
            "drop_example_child"
        ) == 4


def test_workflow_collapses_duplicate_hard_umbrella_capabilities_before_including_but_not_limited_to_examples(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "•对RAG和agent框架有基本了解,包括但不限于 langChain、llama index、autoGen、metaGPT等。"
    description = f"任职要求\n{evidence}\n•熟悉Python语言。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="对RAG和agent框架有基本了解",
            normalized_capability="RAG",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.96,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="对RAG和agent框架有基本了解",
            normalized_capability="Agent Frameworks",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4256_duplicate_hard_umbrella_capabilities",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            RequirementImportance.MUST_HAVE,
            "对RAG和agent框架有基本了解",
            "RAG",
        )
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "drop_exact_duplicate_requirement"
        ]


def test_workflow_keeps_distinct_hard_capabilities_without_including_but_not_limited_to_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉 Agent 和 RAG 相关技术"
    description = f"任职要求\n{original}，并具备 Python 服务开发经验。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Agent",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="RAG",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.94,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_distinct_hard_capabilities_without_example_marker",
        description=description,
    )

    assert [item.normalized_capability for item in proposal.requirements] == ["Agent", "RAG"]


def test_workflow_collapses_nonparenthetical_example_fanout_and_repairs_umbrella_capability(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "3、熟悉大语言模型核心技术,如 Transformer 架构、微调(如 LoRA、PEFT)、AI智能体等;"
    description = f"任职要求\n{evidence}\n4、有实际大模型微调经验。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉大语言模型核心技术,如 Transformer 架构、微调(如 LoRA、PEFT)、AI智能体等",
            normalized_capability="Transformer",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="微调(如 LoRA、PEFT)",
            normalized_capability="LoRA",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.94,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="LoRA、PEFT",
            normalized_capability="PEFT",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.93,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="AI智能体",
            normalized_capability="AI Agent",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.92,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4246_nonparenthetical_examples",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            RequirementImportance.MUST_HAVE,
            "熟悉大语言模型核心技术,如 Transformer 架构、微调(如 LoRA、PEFT)、AI智能体等",
            "大语言模型核心技术",
        )
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert "normalize_umbrella_skill_example_capability" in strategies
        assert strategies.count("drop_example_child") == 3


def test_workflow_keeps_nonparenthetical_example_child_without_same_evidence_parent(
    session_factory: sessionmaker[Session],
) -> None:
    original = "AI智能体"
    evidence = "3、熟悉大语言模型核心技术,如 Transformer 架构、AI智能体等;"
    description = f"任职要求\n{evidence}\n4、有实际大模型微调经验。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="AI Agent",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.92,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_nonparenthetical_example_without_parent",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == [original]


def test_workflow_drops_parenthetical_example_list_child_when_duty_parent_shares_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "2. 基于LangChain、LangGraph、Dify等框架,构建面向研发场景的Agent应用(代码助手、运维助手、文档问答等);"
    description = f"岗位职责\n{evidence}\n3. 负责Prompt工程设计与持续优化。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text="基于LangChain、LangGraph、Dify等框架,构建面向研发场景的Agent应用",
            normalized_capability="LangChain",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text="(代码助手、运维助手、文档问答等)",
            normalized_capability="代码助手",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_parenthetical_example_child_with_duty_parent",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == [
        "基于LangChain、LangGraph、Dify等框架,构建面向研发场景的Agent应用"
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_example_child" in [
            item["strategy"] for item in trace.output["semanticRepairs"]
        ]


def test_workflow_collapses_same_responsibility_capability_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    original = "基于LangChain、LangGraph、Dify等框架,构建面向研发场景的Agent应用"
    evidence = f"2. {original}(代码助手、运维助手、文档问答等);"
    description = f"岗位职责\n{evidence}\n3.负责Prompt工程设计与持续优化。"
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.RESPONSIBILITY,
                original_text=original,
                normalized_capability=capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=evidence,
                confidence=confidence,
            )
            for capability, confidence in (
                ("LangChain", 0.95),
                ("Dify", 0.92),
                ("LangGraph", 0.9),
            )
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_same_responsibility_capability_fanout",
        description=description,
    )

    assert len(proposal.requirements) == 1
    item = proposal.requirements[0]
    assert item.type is RequirementType.RESPONSIBILITY
    assert item.importance is RequirementImportance.MUST_HAVE
    assert item.original_text == original
    assert item.evidence_span == evidence
    assert item.normalized_capability is None
    assert item.confidence == 0.9
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "collapse_responsibility_capability_siblings" in [
            event["strategy"] for event in trace.output["semanticRepairs"]
        ]


def test_workflow_collapses_including_but_not_limited_to_responsibility_enumeration(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "包括但不限于模型路由、负载均衡、推理调度、协议转换等关键子系统。"
    description = f"岗位职责\n1.参与AI平台核心研发。\n{evidence}\n任职要求\n1.本科及以上学历。"
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.RESPONSIBILITY,
                original_text=original,
                normalized_capability=capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=evidence,
                confidence=confidence,
            )
            for original, capability, confidence in (
                ("模型路由", "model routing", 0.96),
                ("负载均衡", "load balancing", 0.95),
                ("推理调度", "inference scheduling", 0.94),
                ("协议转换", "protocol conversion", 0.93),
            )
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_responsibility_enumeration_fanout",
        description=description,
    )

    assert len(proposal.requirements) == 1
    item = proposal.requirements[0]
    assert item.type is RequirementType.RESPONSIBILITY
    assert item.original_text == evidence
    assert item.evidence_span == evidence
    assert item.normalized_capability is None
    assert item.confidence == 0.93
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "collapse_responsibility_enumeration_siblings" in [
            event["strategy"] for event in trace.output["semanticRepairs"]
        ]


def test_workflow_preserves_conjunctive_responsibility_siblings_without_enumeration_marker(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "负责模型路由、负载均衡两个关键子系统。"
    description = f"岗位职责\n{evidence}\n任职要求\n1.本科及以上学历。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text="模型路由",
            normalized_capability="model routing",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text="负载均衡",
            normalized_capability="load balancing",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.94,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_conjunctive_responsibility_siblings",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == ["模型路由", "负载均衡"]


def test_workflow_drops_redundant_responsibility_subclauses_when_full_parent_exists(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "2.主导企业级AI应用与智能体系统设计开发,构建可复用AI能力中台。"
    parent = evidence
    child = "构建可复用AI能力中台"
    description = f"岗位职责\n{evidence}\n任职要求\n1.本科及以上学历。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=child,
            normalized_capability="AI Platform",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.91,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_redundant_responsibility_subclause",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == [parent]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_responsibility_subclause" in [
            event["strategy"] for event in trace.output["semanticRepairs"]
        ]


def test_workflow_drops_numbered_responsibility_subclauses_when_parent_matches_presentation(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "2.主导企业级AI应用与智能体(Agent)系统的设计与开发,构建可复用的AI能力中台。"
    parent = "主导企业级AI应用与智能体(Agent)系统的设计与开发,构建可复用的AI能力中台"
    child = "构建可复用的AI能力中台"
    description = f"岗位职责\n{evidence}\n任职要求\n1.本科及以上学历。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=child,
            normalized_capability="可复用AI能力中台构建",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4272_numbered_responsibility_subclause",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == [parent]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_responsibility_subclause" in {
            event["strategy"] for event in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_responsibility_subclauses_without_full_parent(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "2.主导企业级AI应用与智能体系统设计开发,构建可复用AI能力中台。"
    first = "主导企业级AI应用与智能体系统设计开发"
    second = "构建可复用AI能力中台"
    description = f"岗位职责\n{evidence}\n任职要求\n1.本科及以上学历。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=first,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=second,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.93,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_distinct_responsibility_subclauses_without_parent",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == [first, second]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_responsibility_subclause" not in [
            event["strategy"] for event in trace.output["semanticRepairs"]
        ]


def test_workflow_keeps_single_responsibility_capability_annotation(
    session_factory: sessionmaker[Session],
) -> None:
    original = "负责LangChain Agent服务的性能优化与稳定性治理"
    description = f"岗位职责\n1. {original}。\n任职要求\n1.具备后端开发经验。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=original,
            normalized_capability="LangChain",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.93,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_single_responsibility_capability_annotation",
        description=description,
    )

    assert len(proposal.requirements) == 1
    assert proposal.requirements[0].normalized_capability == "LangChain"


def test_workflow_keeps_example_shaped_item_without_same_evidence_parent(
    session_factory: sessionmaker[Session],
) -> None:
    original = "例如负责模型服务稳定性治理"
    description = (
        f"岗位职责：{original}，并参与监控、告警、故障复盘和持续交付；"
        "任职要求：具备后端服务开发和线上排障经验。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_example_shape_without_parent",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == [original]


def test_workflow_converts_abstract_evaluative_ability_into_mandatory_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "工程能力扎实"
    description = f"任职要求：{original}，至少在以下一个方向非常熟练（会其中一个方向即可）：React、Electron、Python 或工程化。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="engineering ability",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.99,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_abstract_engineering_ability",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]


def test_workflow_drops_atomic_hard_skill_already_covered_by_compound_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    parent = "精通AI常见场景(如预测、决策、NLP、CV等),具备企业级AI系统架构设计能力"
    evidence = f"2.{parent}。"
    child = "具备企业级AI系统架构设计能力"
    description = f"任职要求：\n{evidence}\n3.熟悉智能体技术栈。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.96,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=child,
            normalized_capability="AI系统架构设计",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.94,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_compound_parent_with_redundant_atomic_child",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, parent),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_compound_hard_child" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_concrete_technical_ability_as_skill(
    session_factory: sessionmaker[Session],
) -> None:
    original = "具备企业级AI系统架构设计能力"
    description = f"任职要求：{original}，并具备服务开发、测试与线上排障经验，能够参与方案评审并完成持续交付。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="AI系统架构设计",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_concrete_technical_ability",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            "AI系统架构设计",
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]


def test_workflow_normalizes_compound_responsibility_and_pressure_traits_to_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "具有高度的责任心,并具有较高的抗压能力"
    description = (
        "任职要求\n"
        "7.具有较强的沟通、表达、总结及文档制作能力,具有高度的责任心,并具有较高的抗压能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="抗压能力",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_compound_responsibility_pressure_traits",
        description=description,
    )

    assert proposal.requirements[0].type is RequirementType.CONSTRAINT
    assert proposal.requirements[0].normalized_capability is None
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "abstract_evaluative_skill_constraint" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_compound_traits_with_nonliteral_capability_to_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "具有高度的责任心,并具有较高的抗压能力"
    evidence = "7. 具有较强的沟通、表达、总结及文档制作能力,具有高度的责任心,并具有较高的抗压能力。"
    description = f"岗位要求:\n{evidence}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Responsibility and Stress Management",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4293_compound_traits_nonliteral_capability",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]


def test_workflow_normalizes_standalone_pressure_trait_to_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "具有较高的抗压能力"
    description = f"岗位职责:\n1.负责大模型解决方案设计与交付。\n岗位要求:\n7. {original}。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="抗压能力",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_standalone_pressure_trait",
        description=description,
    )

    assert proposal.requirements[0].type is RequirementType.CONSTRAINT
    assert proposal.requirements[0].normalized_capability is None


def test_workflow_preserves_concrete_compound_technical_skill(
    session_factory: sessionmaker[Session],
) -> None:
    original = "具有较高的Python性能优化能力,并具有较强的分布式系统设计能力"
    description = f"任职要求：{original}，并具备良好的工程实践。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Python性能优化",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_concrete_compound_technical_skill",
        description=description,
    )

    assert proposal.requirements[0].type is RequirementType.SKILL
    assert proposal.requirements[0].normalized_capability == "Python性能优化"


def test_workflow_normalizes_hard_technical_stack_experience_drift_to_skill(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    description = f"【任职要求】\n3.{original},有落地项目经验者优先。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_hard_technical_stack_experience_drift",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            "智能体(Agent)技术栈",
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "normalize_technical_skill_experience_drift" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_split_hard_technical_stack_experience_drift_to_skill(
    session_factory: sessionmaker[Session],
) -> None:
    hard = "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    soft = "有落地项目经验者优先"
    fused = f"{hard},{soft}"
    description = f"3.{fused}。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=fused,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=fused,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4280_split_technical_stack_experience_drift",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            "智能体(Agent)技术栈",
            RequirementImportance.MUST_HAVE,
            hard,
        ),
        (
            RequirementType.EXPERIENCE,
            None,
            RequirementImportance.PREFERRED,
            soft,
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {item["strategy"] for item in trace.output["semanticRepairs"]}
        assert "split_trailing_preferred" in strategies


def test_workflow_normalizes_hard_technical_stack_constraint_drift_to_skill(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    description = f"【任职要求】\n3.{original},有落地项目经验者优先。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_hard_technical_stack_constraint_drift",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            "智能体(Agent)技术栈",
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "normalize_technical_stack_constraint_drift" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_preserves_real_technical_stack_experience_fact(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有智能体技术栈落地项目经验"
    description = f"任职要求：{original}，并具备良好的工程实践、测试意识和跨团队协作能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_real_technical_stack_experience_fact",
        description=description,
    )

    assert proposal.requirements[0].type is RequirementType.EXPERIENCE
    assert proposal.requirements[0].normalized_capability is None
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "normalize_technical_skill_experience_drift" not in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_replaces_example_capability_with_hard_umbrella_skill(
    session_factory: sessionmaker[Session],
) -> None:
    original = "3.熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    description = f"【任职要求】\n{original},有落地项目经验者优先。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="LangChain",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"{original},有落地项目经验者优先。",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4215_example_capability_leak",
        description=description,
    )

    assert proposal.requirements[0].type is RequirementType.SKILL
    assert proposal.requirements[0].importance is RequirementImportance.MUST_HAVE
    assert proposal.requirements[0].normalized_capability == "智能体(Agent)技术栈"
    assert proposal.requirements[0].original_text == original
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "normalize_umbrella_skill_example_capability" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_replaces_full_example_phrase_capability_with_hard_umbrella_skill(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    description = f"任职要求：{original}，有落地项目经验者优先，并具备良好的工程实践能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="智能体(Agent)技术栈(如LangChain、AutoGPT等)",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_full_example_phrase_capability_leak",
        description=description,
    )

    assert proposal.requirements[0].type is RequirementType.SKILL
    assert proposal.requirements[0].importance is RequirementImportance.MUST_HAVE
    assert proposal.requirements[0].normalized_capability == "智能体(Agent)技术栈"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "normalize_umbrella_skill_example_capability" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_replaces_full_example_phrase_plus_soft_experience_capability(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    description = f"任职要求：{original}，有落地项目经验者优先。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="智能体(Agent)技术栈(如LangChain、AutoGPT等),有落地项目经验",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_full_example_phrase_plus_soft_experience_capability",
        description=description,
    )

    assert proposal.requirements[0].normalized_capability == "智能体(Agent)技术栈"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "normalize_umbrella_skill_example_capability" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_extended_hard_capability_without_soft_source_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    description = f"任职要求：{original}，并具备企业级Agent平台架构能力。"
    capability = "智能体(Agent)技术栈(如LangChain、AutoGPT等),企业级Agent平台"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability=capability,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_extended_hard_capability_without_soft_source_evidence",
        description=description,
    )

    assert proposal.requirements[0].normalized_capability == capability


def test_workflow_replaces_presentation_equivalent_full_example_phrase_capability(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    description = f"任职要求：{original}，有落地项目经验者优先。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="智能体（Agent）技术栈（如 LangChain、AutoGPT 等）",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_presentation_equivalent_full_example_capability",
        description=description,
    )

    assert proposal.requirements[0].normalized_capability == "智能体(Agent)技术栈"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "normalize_umbrella_skill_example_capability" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_example_skill_list_as_atomic_skill(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    description = f"任职要求：{original};"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="智能体(Agent)技术栈",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_example_skill_list",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            "智能体(Agent)技术栈",
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]


def test_workflow_collapses_duplicate_example_capability_siblings_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "3.熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    description = f"任职要求：\\n{original},有落地项目经验者优先。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="LangChain",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.9,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="AutoGPT",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.88,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_duplicate_example_capability_siblings",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "collapse_example_skill_siblings"
        ]


def test_workflow_collapses_parenthetical_enum_example_capability_siblings_into_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉主流大模型(GPT 系列 / DeepSeek / Llama / Qwen 等)的技术特性和使用场景"
    description = f"任职要求：{original}。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="GPT",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="DeepSeek",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.94,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Llama",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.93,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Qwen",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.92,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_parenthetical_enum_example_capability_siblings",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "collapse_example_skill_siblings"
        ]


def test_workflow_keeps_parenthetical_capability_list_without_example_marker(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉主流大模型(GPT / Llama)的技术特性"
    description = f"任职要求：{original}，并具备模型服务开发、测试和线上排障经验。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="GPT",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Llama",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.94,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_parenthetical_capability_list_without_example_marker",
        description=description,
    )

    assert [item.normalized_capability for item in proposal.requirements] == [
        "GPT",
        "Llama",
    ]


def test_workflow_splits_hard_skill_prefix_from_inline_cardinality_suffix(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：熟练使用 Python，具备 FrameworkA、FrameworkB 等至少一种智能体框架的实际项目经验，"
        "并能独立完成服务开发、测试与交付。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟练使用 Python，具备 FrameworkA、FrameworkB 等至少一种智能体框架的实际项目经验",
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟练使用 Python，具备 FrameworkA、FrameworkB 等至少一种智能体框架的实际项目经验",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_hard_skill_then_cardinality",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            "Python",
            RequirementImportance.MUST_HAVE,
            "熟练使用 Python",
        ),
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            "具备 FrameworkA、FrameworkB 等至少一种智能体框架的实际项目经验",
        ),
    ]


def test_workflow_splits_education_from_mandatory_experience_clauses(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：本科及以上，计算机相关专业，2年以上开发经验，有智能体应用落地项目经验；"
        "并具备良好的工程实践和协作能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text="本科及以上，计算机相关专业，2年以上开发经验，有智能体应用落地项目经验",
            normalized_capability="本科及以上，计算机相关专业，2年以上开发经验，有智能体应用落地项目经验",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="本科及以上，计算机相关专业，2年以上开发经验，有智能体应用落地项目经验",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_mixed_education_experience",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.EDUCATION,
            None,
            RequirementImportance.MUST_HAVE,
            "本科及以上，计算机相关专业",
        ),
        (
            RequirementType.EXPERIENCE,
            None,
            RequirementImportance.MUST_HAVE,
            "2年以上开发经验",
        ),
        (
            RequirementType.EXPERIENCE,
            None,
            RequirementImportance.MUST_HAVE,
            "有智能体应用落地项目经验",
        ),
    ]


def test_workflow_splits_constraint_type_mixed_education_experience_from_source_candidate(
    session_factory: sessionmaker[Session],
) -> None:
    original = "1.本科及以上学历,计算机、人工智能或汽车工程等相关专业,8年以上AI产品/解决方案经验。"
    description = f"任职要求：\n{original}\n2.熟练使用 Python。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_constraint_mixed_education_experience_source_candidate",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.EDUCATION,
            RequirementImportance.MUST_HAVE,
            "1.本科及以上学历,计算机、人工智能或汽车工程等相关专业",
        ),
        (
            RequirementType.EXPERIENCE,
            RequirementImportance.MUST_HAVE,
            "8年以上AI产品/解决方案经验",
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "split_education_experience"
        ]


def test_workflow_collapses_repaired_inline_alternative_duplicates(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：具备 FrameworkA、FrameworkB、FrameworkC 等至少一种智能体框架的实际项目经验；"
        "并具备良好的工程实践和协作能力。"
    )
    clause = "具备 FrameworkA、FrameworkB、FrameworkC 等至少一种智能体框架的实际项目经验；"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=clause,
            normalized_capability="FrameworkA",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=clause,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=clause,
            normalized_capability="FrameworkB",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=clause,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=clause,
            normalized_capability="FrameworkC",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=clause,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_inline_cardinality_duplicate_repairs",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            clause,
        ),
    ]


def test_workflow_collapses_duplicate_mixed_education_experience_repairs(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：本科及以上，计算机相关专业，2年以上开发经验，有智能体应用落地项目经验；"
        "并具备良好的工程实践和协作能力。"
    )
    mixed_clause = "本科及以上，计算机相关专业，2年以上开发经验，有智能体应用落地项目经验"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=mixed_clause,
            normalized_capability="本科及以上，计算机相关专业",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=mixed_clause,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=mixed_clause,
            normalized_capability="开发经验",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=mixed_clause,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="有智能体应用落地项目经验",
            normalized_capability="智能体应用落地",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="有智能体应用落地项目经验",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_duplicate_mixed_education_experience",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.EDUCATION, RequirementImportance.MUST_HAVE, "本科及以上，计算机相关专业"),
        (RequirementType.EXPERIENCE, RequirementImportance.MUST_HAVE, "2年以上开发经验"),
        (RequirementType.EXPERIENCE, RequirementImportance.MUST_HAVE, "有智能体应用落地项目经验"),
    ]


def test_workflow_collapses_repaired_atomic_requirement_with_parent_evidence_duplicate(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：1.本科及以上学历,计算机、人工智能或汽车工程等相关专业,8年以上AI产品/解决方案经验。"
        "2.具备企业级AI系统架构设计能力并有良好的跨部门协作能力。"
    )
    mixed_clause = "本科及以上学历,计算机、人工智能或汽车工程等相关专业,8年以上AI产品/解决方案经验"
    parent_clause = f"1.{mixed_clause}。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=mixed_clause,
            normalized_capability="本科及以上学历",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_clause,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="8年以上AI产品/解决方案经验",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_clause,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_parent_evidence_duplicate",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.EDUCATION, RequirementImportance.MUST_HAVE, "本科及以上学历,计算机、人工智能或汽车工程等相关专业"),
        (RequirementType.EXPERIENCE, RequirementImportance.MUST_HAVE, "8年以上AI产品/解决方案经验"),
    ]


def test_workflow_collapses_repaired_atomic_requirement_despite_trailing_punctuation(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：1.本科及以上学历,计算机、人工智能或汽车工程等相关专业,8年以上AI产品/解决方案经验。"
        "2.具备企业级AI系统架构设计能力并有良好的跨部门协作能力。"
    )
    mixed_clause = "本科及以上学历,计算机、人工智能或汽车工程等相关专业,8年以上AI产品/解决方案经验"
    parent_clause = f"1.{mixed_clause}。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=mixed_clause,
            normalized_capability="本科及以上学历",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_clause,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="8年以上AI产品/解决方案经验。",
            normalized_capability="AI",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_clause,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_parent_evidence_duplicate_punctuation",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.EDUCATION, RequirementImportance.MUST_HAVE, "本科及以上学历,计算机、人工智能或汽车工程等相关专业"),
        (RequirementType.EXPERIENCE, RequirementImportance.MUST_HAVE, "8年以上AI产品/解决方案经验"),
    ]


def test_workflow_deduplicates_punctuation_equivalent_hard_constraints(
    session_factory: sessionmaker[Session],
) -> None:
    without_terminal = (
        "3. 熟悉Prompt工程,能独立设计结构化Prompt,具备上下文管理与复杂意图拆解能力"
    )
    with_terminal = f"{without_terminal};"
    description = f"任职要求\n{with_terminal}\n4. 理解RAG、向量数据库、Function Calling等核心技术。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=without_terminal,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=without_terminal,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=with_terminal,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=with_terminal,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_punctuation_equivalent_hard_constraint",
        description=description,
    )

    assert len(proposal.requirements) == 1
    assert proposal.requirements[0].type is RequirementType.CONSTRAINT
    assert proposal.requirements[0].importance is RequirementImportance.MUST_HAVE
    assert proposal.requirements[0].original_text == without_terminal
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_exact_duplicate_requirement" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_deduplicates_soft_same_source_capability_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有MCP协议实践、研发效能/DevOps工具链经验,或熟练使用Cursor、Claude Code等AI工具链者优先"
    evidence = f"6. {original}。"
    description = f"任职要求\n{evidence}"
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=original,
                normalized_capability=capability,
                importance=RequirementImportance.PREFERRED,
                evidence_span=evidence,
                confidence=0.95,
            )
            for capability in ("MCP Protocol", "DevOps", "Cursor", "Claude Code")
        )
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4249_soft_capability_fanout",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            RequirementImportance.PREFERRED,
            original,
            "MCP Protocol",
        )
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]].count(
            "drop_exact_duplicate_requirement"
        ) == 3


def test_workflow_normalizes_provider_bonus_for_explicit_preferred_alternative_clause(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有MCP协议实践、研发效能/DevOps工具链经验,或熟练使用Cursor、Claude Code等AI工具链者优先"
    evidence = f"6. {original}。"
    description = f"任职要求\n{evidence}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="MCP Protocol",
            importance=RequirementImportance.BONUS,
            evidence_span=evidence,
            confidence=0.95,
        )
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4292_preferred_clause_false_bonus",
        description=description,
    )

    assert len(proposal.requirements) == 1
    assert proposal.requirements[0].type is RequirementType.SKILL
    assert proposal.requirements[0].importance is RequirementImportance.PREFERRED
    assert proposal.requirements[0].normalized_capability == "MCP Protocol"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "explicit_soft_marker_preferred" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_preserves_bonus_importance_inside_explicit_bonus_section(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉MCP协议者优先"
    evidence = f"1. {original}"
    description = (
        f"三、加分项(满足越多越优先)\n{evidence}\n"
        "2. 有相关开源项目贡献经验\n3. 熟悉团队协作和工程交付流程"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="MCP协议",
            importance=RequirementImportance.BONUS,
            evidence_span=evidence,
            confidence=0.95,
        )
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_explicit_bonus_section_preferred_wording_preserved",
        description=description,
    )

    assert len(proposal.requirements) == 1
    assert proposal.requirements[0].importance is RequirementImportance.BONUS


def test_workflow_deduplicates_full_line_bonus_section_capability_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    engine_bonus = "熟悉 vLLM / TGI / Triton Inference Server 等推理引擎"
    engine_evidence = f"4. {engine_bonus}"
    optimization_bonus = "有 CUDA 编程或模型推理优化经验"
    optimization_evidence = f"5. {optimization_bonus}"
    description = (
        "二、任职要求\n"
        "1. 熟练使用 Python\n"
        "三、加分项(满足越多越优先)\n"
        f"{engine_evidence}\n"
        f"{optimization_evidence}\n"
        "6. 发表过 AI/ML 领域顶会论文或主导过知名开源项目"
    )
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=engine_bonus,
                normalized_capability=capability,
                importance=RequirementImportance.BONUS,
                evidence_span=engine_evidence,
                confidence=0.95,
            )
            for capability in ("vLLM", "TGI", "Triton Inference Server")
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=optimization_bonus,
                normalized_capability=capability,
                importance=RequirementImportance.BONUS,
                evidence_span=optimization_evidence,
                confidence=0.94,
            )
            for capability in ("CUDA", "Model inference optimization")
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4291_bonus_full_line_capability_fanout",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.SKILL,
            RequirementImportance.BONUS,
            engine_bonus,
            "vLLM",
        ),
        (
            RequirementType.SKILL,
            RequirementImportance.BONUS,
            optimization_bonus,
            "CUDA",
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]].count(
            "drop_exact_duplicate_requirement"
        ) == 3


def test_workflow_preserves_distinct_atomic_bonus_capabilities_with_shared_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    bonus_line = "4. 熟悉 vLLM / TGI / Triton Inference Server 等推理引擎"
    description = f"三、加分项(满足越多越优先)\n{bonus_line}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="vLLM",
            normalized_capability="vLLM",
            importance=RequirementImportance.BONUS,
            evidence_span=bonus_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="TGI",
            normalized_capability="TGI",
            importance=RequirementImportance.BONUS,
            evidence_span=bonus_line,
            confidence=0.94,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_bonus_atomic_capabilities_preserved",
        description=description,
    )

    assert [item.normalized_capability for item in proposal.requirements] == ["vLLM", "TGI"]


def test_workflow_deduplicates_cardinality_child_capability_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    header = "至少覆盖以下方向中的 两项:"
    child = "模型微调(SFT / LoRA / QLoRA)"
    description = (
        "任职要求:\n"
        f"3 具备 LLM 应用工程实战经验,{header}\n"
        f"\uf06c {child}\n"
        "\uf06c RAG 架构设计(文本切分策略、召回排序、向量数据库选型)\n"
        "\uf06c Agent / 智能体开发(工具调用、多轮规划、多 Agent 协作)\n"
        "\uf06c Prompt Engineering 系统化实践(Few-shot、Chain-of-Thought、结构化输出)\n"
        "4 熟练使用 PyTorch 或 TensorFlow,并具备良好的工程实践。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=header,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=header,
            confidence=0.98,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=child,
                normalized_capability=capability,
                importance=RequirementImportance.PREFERRED,
                evidence_span=child,
                confidence=0.95,
            )
            for capability in ("模型微调", "LoRA", "QLoRA")
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4250_cardinality_child_capability_fanout",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            RequirementImportance.MUST_HAVE,
            header,
            None,
        ),
        (
            RequirementType.SKILL,
            RequirementImportance.PREFERRED,
            child,
            "模型微调",
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]].count(
            "drop_exact_duplicate_requirement"
        ) == 2


def test_workflow_keeps_hard_same_source_distinct_capability_annotations(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉模型训练与推理优化"
    description = f"任职要求\n1. {original}。\n2. 具备良好的工程实践、测试意识与线上问题排查能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="模型训练",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="推理优化",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.94,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_hard_same_source_distinct_capabilities",
        description=description,
    )

    assert [item.normalized_capability for item in proposal.requirements] == [
        "模型训练",
        "推理优化",
    ]


def test_workflow_keeps_unsoftened_preferred_same_source_distinct_capabilities(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉 Agent 和 RAG 相关技术"
    description = (
        "岗位要求\n"
        f"1. {original}。\n"
        "2. 具备良好的工程实践、测试意识与线上问题排查能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Agent",
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="RAG",
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=0.94,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_preferred_same_source_distinct_capabilities",
        description=description,
    )

    assert [item.normalized_capability for item in proposal.requirements] == [
        "Agent",
        "RAG",
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

    assert proposal.extractor_version == "requirement-extractor-v42.95"
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
        assert trace.output["semanticPolicyVersion"] == "requirement-semantics-v42.96"
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


def test_workflow_promotes_unsoftened_preferred_item_in_explicit_requirement_section(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉基于DeepSeek的微调、训练、建立智能体应用"
    description = (
        "岗位职责:\n"
        "1. 负责大模型解决方案设计、售前推进和方案落地。\n"
        "岗位要求:\n"
        "1. 了解国内外主流大模型技术。\n"
        f"2. {original}。\n"
        "3. 熟悉主流AI应用开发框架。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="DeepSeek",
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_requirement_section_false_preferred",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.MUST_HAVE
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "requirement_section_default_must_have"
        ]


def test_workflow_promotes_unsoftened_preferred_education_in_explicit_requirement_section(
    session_factory: sessionmaker[Session],
) -> None:
    original = "知名高校本科及以上学历"
    evidence = f"2.{original}。"
    description = (
        "【任职要求】\n"
        "1. 2 年以上软件开发经验,特别优秀者可放宽(不限年限)\n"
        f"{evidence}\n"
        "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可)。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4258_education_false_preferred",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.MUST_HAVE
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "requirement_section_default_must_have"
        ]


def test_workflow_promotes_unsoftened_preferred_experience_threshold_in_requirement_section(
    session_factory: sessionmaker[Session],
) -> None:
    original = "3 年以上工作经验(研究生期间参与的实际项目经验可计入)"
    evidence = f"1 {original}"
    description = (
        "二、任职要求\n"
        "2. 工作经验\n"
        f"{evidence}\n"
        "2 有至少一个从 0 到 1 完整交付的产品化项目经历,能够清晰描述自己在其中的角色和贡献\n"
        "3. 编程与工程能力\n"
        "1 精通 Python 或 Go 或 Java 至少一门语言,具备良好的工程规范和代码品味"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability="3+ Years of Work Experience",
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4274_experience_threshold_false_preferred",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.MUST_HAVE
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "requirement_section_default_must_have"
        ]


def test_workflow_keeps_explicitly_softened_experience_threshold_preferred_in_requirement_section(
    session_factory: sessionmaker[Session],
) -> None:
    original = "3 年以上工作经验者优先"
    description = (
        "任职要求:\n"
        f"1. {original}\n"
        "2. 熟练使用 Python 并能独立完成服务开发、测试和线上排障。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_soft_experience_threshold_preferred",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.PREFERRED


def test_workflow_keeps_explicitly_softened_education_preferred_in_requirement_section(
    session_factory: sessionmaker[Session],
) -> None:
    original = "知名高校本科及以上学历者优先"
    description = (
        "【任职要求】\n"
        f"2.{original}。\n"
        "3.熟练使用 Python 并能独立完成服务开发、测试和线上排障。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_soft_education_preferred",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.PREFERRED


def test_workflow_promotes_explicit_application_material_requirement_from_bonus(
    session_factory: sessionmaker[Session],
) -> None:
    original = "投递简历请附带 GitHub ID(或其他开源网站/邮件列表的个人页面地址)"
    description = (
        "任职要求:\n"
        "1.计算机相关专业,本科及以上学历;\n"
        "10.优秀的沟通能力,能够与产品、后端、算法等不同背景的团队成员高效协作。\n"
        f"{original}"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=original,
            normalized_capability="GitHub",
            importance=RequirementImportance.BONUS,
            evidence_span=original,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4271_application_material_false_bonus",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "promote_application_material_requirement"
        ]


def test_workflow_keeps_nonimperative_github_bonus_soft(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有活跃 GitHub 或开源社区贡献者优先"
    description = (
        "任职要求:\n"
        "1.熟练使用 Python。\n"
        f"加分项: {original}。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=original,
            normalized_capability="GitHub",
            importance=RequirementImportance.BONUS,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_github_bonus_not_application_material",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.BONUS


def test_workflow_promotes_numbered_unsoftened_requirement_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟练使用 Docker、Kubernetes,理解云原生的核心设计理念"
    evidence = f"4 {original}"
    description = (
        "二、任职要求\n"
        "3. 编程与工程能力\n"
        f"{evidence}\n"
        "4. AI 技术能力\n"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_numbered_requirement_false_preferred",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.MUST_HAVE


def test_workflow_promotes_source_candidate_anchored_hard_requirement_before_compound_normalization(
    session_factory: sessionmaker[Session],
) -> None:
    original = "理解RAG、向量数据库、Function Calling等核心技术,能独立完成原型验证与方案评估"
    evidence = f"4. {original};"
    description = (
        "岗位职责:\n"
        "1. 负责 Agent 应用研发。\n"
        "任职要求\n"
        f"{evidence}\n"
        "5. 具备良好的研发场景理解与快速学习能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="RAG, vector database, Function Calling",
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_source_candidate_false_preferred_compound_hard_requirement",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]] == [
            "requirement_section_default_must_have",
            "compound_hard_skill_constraint",
        ]


def test_workflow_keeps_explicitly_softened_item_preferred_in_requirement_section(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉基于DeepSeek的微调、训练、建立智能体应用者优先"
    description = (
        "岗位要求:\n"
        f"1. {original}。\n"
        "2. 熟练使用 Python 并能独立完成服务开发、测试和线上排障。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="DeepSeek",
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_requirement_section_true_preferred",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.PREFERRED


def test_workflow_does_not_promote_preferred_item_from_responsibility_section(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉基于DeepSeek的微调、训练、建立智能体应用"
    description = (
        "岗位职责:\n"
        f"1. {original}。\n"
        "岗位要求:\n"
        "1. 熟练使用 Python 并能独立完成服务开发、测试和线上排障。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="DeepSeek",
            importance=RequirementImportance.PREFERRED,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_responsibility_section_preferred",
        description=description,
    )

    assert proposal.requirements[0].importance is RequirementImportance.PREFERRED


def test_workflow_promotes_hard_experience_prefix_when_soft_sibling_shares_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = (
        "5.有成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径者优先。 "
        "需要有车端经验,非车端经验的无法到副总师的层级"
    )
    hard = "有成功主导千万级以上AI项目的经验"
    soft = "熟悉车企数字化转型路径者优先"
    description = f"任职要求：\n{evidence}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=hard,
            normalized_capability="AI project leadership",
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=soft,
            normalized_capability="车企数字化转型路径",
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.9,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="需要有车端经验",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="需要有车端经验",
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_hard_experience_prefix_with_soft_sibling",
        description=description,
    )

    assert [(item.original_text, item.importance) for item in proposal.requirements] == [
        (hard, RequirementImportance.MUST_HAVE),
        (soft, RequirementImportance.PREFERRED),
        ("需要有车端经验", RequirementImportance.MUST_HAVE),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "promote_hard_experience_prefix_before_soft_sibling" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_preferred_experience_prefix_when_soft_sibling_is_alternative(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "有支付平台经验,或熟悉风控系统者优先"
    hard = "有支付平台经验"
    soft = "熟悉风控系统者优先"
    description = (
        f"任职要求：{evidence}。"
        "同时需要具备稳定的服务交付经验，并能参与测试、上线和故障复盘。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=hard,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.92,
        ),
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=soft,
            normalized_capability="风控系统",
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_preferred_experience_alternative_soft_sibling",
        description=description,
    )

    assert [(item.original_text, item.importance) for item in proposal.requirements] == [
        (hard, RequirementImportance.PREFERRED),
        (soft, RequirementImportance.PREFERRED),
    ]


def test_workflow_splits_must_have_clause_when_trailing_preferred_already_exists(
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
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="熟悉消息队列技术栈，有大型项目落地经验者优先",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="有大型项目落地经验者优先。",
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span="有大型项目落地经验者优先。",
            confidence=0.9,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="有主导大型平台项目的经验，熟悉金融业务者优先",
            normalized_capability="大型平台项目经验",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="有主导大型平台项目的经验，熟悉金融业务者优先",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text="熟悉金融业务者优先。",
            normalized_capability="金融业务",
            importance=RequirementImportance.PREFERRED,
            evidence_span="熟悉金融业务者优先。",
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_must_have_trailing_preferred",
        description=description,
    )

    assert [(item.original_text, item.importance) for item in proposal.requirements] == [
        ("熟悉消息队列技术栈", RequirementImportance.MUST_HAVE),
        ("有大型项目落地经验者优先。", RequirementImportance.PREFERRED),
        ("有主导大型平台项目的经验", RequirementImportance.MUST_HAVE),
        ("熟悉金融业务者优先。", RequirementImportance.PREFERRED),
    ]


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


def test_workflow_splits_embedded_preferred_clause_when_trailing_hard_fact_is_already_covered(
    session_factory: sessionmaker[Session],
) -> None:
    full = (
        "5.有成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径者优先。 "
        "需要有车端经验,非车端经验的无法到副总师的层级"
    )
    description = f"任职要求：\n{full}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=full,
            normalized_capability="成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径",
            importance=RequirementImportance.PREFERRED,
            evidence_span=full,
            confidence=0.96,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="需要有车端经验",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="需要有车端经验",
            confidence=0.99,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_embedded_preferred_with_covered_tail",
        description=description,
    )

    assert [
        (item.type, item.original_text, item.importance, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.EXPERIENCE,
            "5.有成功主导千万级以上AI项目的经验",
            RequirementImportance.MUST_HAVE,
            None,
        ),
        (
            RequirementType.SKILL,
            "熟悉车企数字化转型路径者优先",
            RequirementImportance.PREFERRED,
            "车企数字化转型路径",
        ),
        (
            RequirementType.EXPERIENCE,
            "需要有车端经验",
            RequirementImportance.MUST_HAVE,
            None,
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]].count(
            "split_embedded_preferred_with_covered_tail"
        ) == 1


def test_workflow_splits_must_have_embedded_preferred_clause_and_collapses_duplicate_hard_prefix(
    session_factory: sessionmaker[Session],
) -> None:
    full = (
        "5.有成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径者优先。 "
        "需要有车端经验,非车端经验的无法到副总师的层级"
    )
    hard_prefix = "5.有成功主导千万级以上AI项目的经验"
    description = f"任职要求：\\n{full}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=full,
            normalized_capability="AI",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=full,
            confidence=0.96,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=hard_prefix,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=hard_prefix,
            confidence=0.9,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉车企数字化转型路径者优先",
            normalized_capability="车企数字化转型路径",
            importance=RequirementImportance.PREFERRED,
            evidence_span="熟悉车企数字化转型路径者优先",
            confidence=0.9,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="需要有车端经验",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="需要有车端经验",
            confidence=0.99,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_must_have_embedded_preferred_with_duplicate_prefix",
        description=description,
    )

    assert [
        (item.type, item.original_text, item.importance, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.EXPERIENCE,
            hard_prefix,
            RequirementImportance.MUST_HAVE,
            None,
        ),
        (
            RequirementType.SKILL,
            "熟悉车企数字化转型路径者优先",
            RequirementImportance.PREFERRED,
            "车企数字化转型路径",
        ),
        (
            RequirementType.EXPERIENCE,
            "需要有车端经验",
            RequirementImportance.MUST_HAVE,
            None,
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert "normalize_experience_type_drift" in strategies
        assert "split_embedded_preferred_with_covered_tail" in strategies
        assert "drop_exact_duplicate_requirement" in strategies


def test_workflow_splits_must_have_embedded_preferred_item_when_trailing_hard_fact_is_not_covered(
    session_factory: sessionmaker[Session],
) -> None:
    full = (
        "5.有成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径者优先。 "
        "需要有车端经验,非车端经验的无法到副总师的层级"
    )
    description = f"任职要求：\\n{full}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=full,
            normalized_capability="AI",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=full,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_must_have_embedded_preferred_without_covered_tail",
        description=description,
    )

    assert [
        (item.type, item.original_text, item.importance)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.EXPERIENCE,
            "5.有成功主导千万级以上AI项目的经验",
            RequirementImportance.MUST_HAVE,
        ),
        (
            RequirementType.SKILL,
            "熟悉车企数字化转型路径者优先",
            RequirementImportance.PREFERRED,
        ),
        (
            RequirementType.EXPERIENCE,
            "需要有车端经验",
            RequirementImportance.MUST_HAVE,
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "split_hard_preferred_hard_mixed_scope" in {
            item["strategy"] for item in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_embedded_preferred_item_when_trailing_hard_fact_is_not_covered(
    session_factory: sessionmaker[Session],
) -> None:
    full = (
        "5.有成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径者优先。 "
        "需要有车端经验,非车端经验的无法到副总师的层级"
    )
    description = f"任职要求：\n{full}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=full,
            normalized_capability="成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径",
            importance=RequirementImportance.PREFERRED,
            evidence_span=full,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_embedded_preferred_without_covered_tail",
        description=description,
    )

    assert len(proposal.requirements) == 1
    assert proposal.requirements[0].original_text == full
    assert proposal.requirements[0].importance is RequirementImportance.PREFERRED


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


def test_workflow_downgrades_repeated_child_name_when_unique_inside_alternative_scope(
    session_factory: sessionmaker[Session],
) -> None:
    description = (
        "任职要求：\n"
        "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):\n"
        "【前端方向】:React、TypeScript、复杂交互。\n"
        "【后端方向】:Python、异步模型、测试工程化。\n"
        "4.不要求 React / Python 两个方向都精通,但至少要能独立 owner 一个核心方向。\n"
        "5.熟练使用 AI Agent 工具进行真实软件开发。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text="工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可)",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可)",
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="React",
            normalized_capability="React",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="React",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="TypeScript",
            normalized_capability="TypeScript",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="TypeScript",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="Python",
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="Python",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="不要求 React / Python 两个方向都精通,但至少要能独立 owner 一个核心方向",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="不要求 React / Python 两个方向都精通,但至少要能独立 owner 一个核心方向",
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_repeated_child_inside_alternative_scope",
        description=description,
    )

    assert [item.importance for item in proposal.requirements] == [
        RequirementImportance.MUST_HAVE,
        RequirementImportance.PREFERRED,
        RequirementImportance.PREFERRED,
        RequirementImportance.PREFERRED,
        RequirementImportance.MUST_HAVE,
    ]


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


def test_workflow_normalizes_action_shaped_responsibility_skill_drift(
    session_factory: sessionmaker[Session],
) -> None:
    original = "主导企业级AI应用与智能体系统的设计与开发,构建可复用的AI能力中台。"
    description = (
        f"{original}\n"
        "任职要求\n1.本科及以上学历,计算机相关专业。\n2.熟悉 Python。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Enterprise AI Development",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_responsibility_skill_drift",
        description=description,
    )

    assert [(item.type, item.normalized_capability) for item in proposal.requirements] == [
        (RequirementType.RESPONSIBILITY, None),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "responsibility_type_normalization" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_explicit_technical_qualification_as_skill(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉企业级AI系统架构设计,能够独立完成方案评审与落地。"
    description = f"任职要求\n1.{original}\n2.具备两年以上相关开发经验。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="AI Architecture",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_explicit_technical_qualification",
        description=description,
    )

    assert proposal.requirements[0].type is RequirementType.CONSTRAINT
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {repair["strategy"] for repair in trace.output["semanticRepairs"]}
        assert "compound_hard_skill_constraint" in strategies
        assert "responsibility_type_normalization" not in strategies


def test_workflow_splits_constraint_hard_skill_prefix_from_cardinality_group(
    session_factory: sessionmaker[Session],
) -> None:
    original = "2. 熟练使用Python,具备LangChain、LangGraph、Dify等至少一种Agent框架的实际项目经验;"
    description = (
        "任职要求\n"
        f"{original}\n"
        "3. 熟悉Prompt工程,能独立完成结构化Prompt设计与上下文管理。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_constraint_python_cardinality",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance) for item in proposal.requirements] == [
        (RequirementType.SKILL, "Python", RequirementImportance.MUST_HAVE),
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE),
    ]
    assert proposal.requirements[0].original_text == "2. 熟练使用Python"
    assert "至少一种Agent框架" in proposal.requirements[1].original_text


def test_workflow_normalizes_non_experience_ability_qualification_from_experience(
    session_factory: sessionmaker[Session],
) -> None:
    original = "5. 具备良好的研发场景理解与快速学习能力,能将业务需求转化为可落地的Agent方案;"
    description = (
        "任职要求\n"
        f"{original}\n"
        "6. 有两年以上研发平台开发经验。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.92,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_non_experience_ability_drift",
        description=description,
    )

    assert [(item.type, item.importance) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "non_experience_qualification_constraint" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_drops_exact_cross_type_evaluator_duplicates(
    session_factory: sessionmaker[Session],
) -> None:
    skill_text = "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    experience_text = "有成功主导千万级以上AI项目的经验"
    description = (
        "任职要求\n"
        f"1.{skill_text}\n"
        f"2.{experience_text}\n"
        "3.具备良好的沟通与协作能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=skill_text,
            normalized_capability="Agent technology stack",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=skill_text,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=skill_text,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=skill_text,
            confidence=0.9,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=experience_text,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=experience_text,
            confidence=0.96,
        ),
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=experience_text,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=experience_text,
            confidence=0.88,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_cross_type_duplicates",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.SKILL, skill_text),
        (RequirementType.EXPERIENCE, experience_text),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        ]
        assert strategies.count("drop_redundant_cross_type_duplicate") == 1
        assert "normalize_experience_type_drift" in strategies
        assert "drop_exact_duplicate_requirement" in strategies


def test_workflow_collapses_formal_case_12_cross_importance_experience_duplicate(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有 Agent / 多模态 / RAG 系统实际开发经验;"
    evidence = f"- {original}"
    description = (
        "岗位要求\n"
        "- 3年以上AI相关研发经验\n"
        "加分项\n"
        f"{evidence}\n"
        "- GitHub 有开源项目或技术博客者优先。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.99,
        ),
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.99,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_formal_case_12_cross_importance_experience_duplicate",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.EXPERIENCE, RequirementImportance.BONUS, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_cross_type_duplicate" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_collapses_live_experience_ability_cross_type_and_soft_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    original = (
        "有实际大模型微调经验,能基于开源基座大模型完成模型的二次训练"
        "(大语言模型或多模态大模型)"
    )
    evidence = f"4、{original}。"
    description = f"【任职要求】\n{evidence}\n5、熟悉 Python 服务开发。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability="Large Language Model Fine-Tuning",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Open Source LLM",
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Multimodal Model",
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4264_experience_ability_fanout",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.EXPERIENCE, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        ]
        assert strategies.count("drop_redundant_cross_type_duplicate") == 3


def test_workflow_keeps_experience_ability_fanout_when_source_is_explicitly_soft(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有大模型微调经验,能独立完成模型二次训练"
    evidence = f"{original},相关经验者优先。"
    description = f"【任职要求】\n{evidence}\n熟悉 Python 服务开发。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability="LLM Fine-Tuning",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="Model Training",
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_soft_experience_ability_fanout_boundary",
        description=description,
    )

    assert len(proposal.requirements) == 2


def test_workflow_keeps_distinct_experience_and_skill_originals_in_same_line(
    session_factory: sessionmaker[Session],
) -> None:
    experience_text = "有大模型微调经验"
    skill_text = "能独立完成模型二次训练"
    evidence = f"{experience_text},{skill_text}。"
    description = f"【任职要求】\n{evidence}\n熟悉 Python 服务开发。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=experience_text,
            normalized_capability="LLM Fine-Tuning",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=skill_text,
            normalized_capability="Model Training",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_distinct_experience_and_skill_originals",
        description=description,
    )

    assert {item.original_text for item in proposal.requirements} == {
        experience_text,
        skill_text,
    }


def test_workflow_rejects_near_total_explicit_bonus_section_coverage_loss(
    session_factory: sessionmaker[Session],
) -> None:
    qualification = "硕士及以上学历,计算机相关专业"
    bonus_items = (
        "1. 做过团队 leader",
        "2. 有 AI 网关 / API 网关研发经验",
        "3. 有多模型编排与融合调度相关项目经验",
        "4. 熟悉 vLLM / TGI / Triton Inference Server 等推理引擎",
        "5. 有 CUDA 编程或模型推理优化经验",
        "6. 发表过 AI/ML 领域顶会论文或主导过知名开源项目",
        "7. 有 toB 产品研发经验",
    )
    description = "\n".join(
        ("任职要求", qualification, "三、加分项(满足越多越优先)", *bonus_items)
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=qualification,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=qualification,
            confidence=0.98,
        ),
    )

    with pytest.raises(InvalidRequirementExtractorOutputError) as captured:
        _workflow(session_factory, extractor).execute(
            job_id="job_explicit_bonus_section_coverage_loss",
            description=description,
        )

    assert "explicit bonus coverage too low" in str(captured.value)
    with session_factory() as session:
        trace = session.get(TraceSpanORM, captured.value.run_id)
        assert trace is not None
        assert trace.error is not None
        assert trace.output["coveragePolicyVersion"] == "requirement-coverage-v4"


def test_workflow_does_not_enforce_bonus_coverage_for_small_bonus_section(
    session_factory: sessionmaker[Session],
) -> None:
    qualification = "本科及以上学历,计算机相关专业"
    description = "\n".join(
        (
            "任职要求",
            qualification,
            "加分项:",
            "1. 有开源项目经验",
            "2. 有 AI 网关研发经验",
            "3. 熟悉 CUDA",
        )
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=qualification,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=qualification,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_small_bonus_section",
        description=description,
    )
    assert proposal.extractor_version == "requirement-extractor-v42.95"


def test_workflow_rejects_near_total_responsibility_coverage_loss(
    session_factory: sessionmaker[Session],
) -> None:
    duties = (
        "1.深入汽车制造、供应链、智能驾驶等业务场景,挖掘高价值AI应用机会,设计落地路径。",
        "2.主导企业级AI应用与智能体(Agent)系统的设计与开发,构建可复用的AI能力中台。",
        "3.协同业务部门推进AI场景试点与规模化推广,实现效率提升或商业价值转化。",
        "跟踪AI技术与行业趋势,规划AI技术路线图,推动创新技术融入主营业务。",
        "4.制定AI工程标准与规范,推动敏捷交付与持续集成。",
        "5.主导企业级AI应用与智能体(Agent)的全生命周期开发,包括需求分析、方案设计、原型开发、落地验证及迭代优化。",
    )
    qualification = "本科及以上学历,计算机、人工智能或汽车工程等相关专业"
    description = "\n".join((*duties, "任职要求", qualification, "8年以上AI产品/解决方案经验。"))
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=qualification,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=qualification,
            confidence=0.98,
        ),
    )

    with pytest.raises(InvalidRequirementExtractorOutputError) as captured:
        _workflow(session_factory, extractor).execute(
            job_id="job_near_total_responsibility_coverage_loss",
            description=description,
        )

    assert "responsibility coverage too low" in str(captured.value)
    with session_factory() as session:
        trace = session.get(TraceSpanORM, captured.value.run_id)
        assert trace is not None
        assert trace.error is not None
        assert trace.output["coveragePolicyVersion"] == "requirement-coverage-v4"
        assert trace.output["coverageAudit"] == {
            "dutyCandidateCount": 6,
            "coveredDutyCount": 0,
            "minimumCoveredDutyCount": 2,
            "enforced": True,
        }


def test_workflow_allows_partial_responsibility_coverage_above_fail_closed_floor(
    session_factory: sessionmaker[Session],
) -> None:
    duties = (
        "1.深入汽车制造、供应链、智能驾驶等业务场景,挖掘高价值AI应用机会,设计落地路径。",
        "2.主导企业级AI应用与智能体(Agent)系统的设计与开发,构建可复用的AI能力中台。",
        "3.协同业务部门推进AI场景试点与规模化推广,实现效率提升或商业价值转化。",
        "跟踪AI技术与行业趋势,规划AI技术路线图,推动创新技术融入主营业务。",
        "4.制定AI工程标准与规范,推动敏捷交付与持续集成。",
        "5.主导企业级AI应用与智能体(Agent)的全生命周期开发,包括需求分析、方案设计、原型开发、落地验证及迭代优化。",
    )
    qualification = "本科及以上学历,计算机相关专业"
    description = "\n".join((*duties, "任职要求", qualification, "具备8年以上AI产品经验。"))
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=duties[0],
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=duties[0],
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=duties[1],
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=duties[1],
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=qualification,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=qualification,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_partial_responsibility_coverage",
        description=description,
    )

    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert trace.error is None
        assert trace.output["coverageAudit"] == {
            "dutyCandidateCount": 6,
            "coveredDutyCount": 2,
            "minimumCoveredDutyCount": 2,
            "enforced": True,
        }


def test_workflow_does_not_enforce_coverage_gate_for_fewer_than_four_duty_lines(
    session_factory: sessionmaker[Session],
) -> None:
    duties = (
        "1.主导企业级AI应用方案设计,推动方案评审与落地交付。",
        "2.协同业务团队推进AI场景试点,持续跟踪应用效果与改进项。",
        "3.制定AI工程规范,推动测试、监控与持续集成体系建设。",
    )
    qualification = "本科及以上学历,计算机相关专业"
    description = "\n".join((*duties, "任职要求", qualification, "具备三年以上软件开发经验。"))
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=qualification,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=qualification,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_small_responsibility_section",
        description=description,
    )

    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert trace.output["coverageAudit"] == {
            "dutyCandidateCount": 3,
            "coveredDutyCount": 0,
            "minimumCoveredDutyCount": 0,
            "enforced": False,
        }


def test_workflow_ignores_numbered_responsibility_group_headings_and_counts_labeled_duties(
    session_factory: sessionmaker[Session],
) -> None:
    grouped_duties = (
        ("1. 核心AI引擎设计与实现", "混合知识引擎构建: 设计并实现融合RAG与知识图谱的混合知识引擎,支持复杂知识推理。"),
        ("2. RAG系统深度优化", "检索系统架构: 设计高性能检索系统架构,持续优化召回与重排序链路。"),
        ("3. 提示工程与模型优化", "高级提示工程: 设计并实现复杂提示工程策略,提升结构化输出稳定性。"),
        ("4. 前沿技术探索与落地", "创新方案设计: 结合业务需求设计AI应用方案,推动技术在实际场景中落地。"),
    )
    qualification = "本科及以上学历,计算机相关专业"
    description = "\n".join(
        (
            "岗位职责:",
            *(line for pair in grouped_duties for line in pair),
            "任职要求:",
            qualification,
        )
    )
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.RESPONSIBILITY,
                original_text=duty.split(":", 1)[1].strip(),
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=duty,
                confidence=0.95,
            )
            for _, duty in grouped_duties
        ),
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=qualification,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=qualification,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_grouped_responsibility_coverage",
        description=description,
    )

    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert trace.error is None
        assert trace.output["coveragePolicyVersion"] == "requirement-coverage-v4"
        assert trace.output["coverageAudit"] == {
            "dutyCandidateCount": 4,
            "coveredDutyCount": 4,
            "minimumCoveredDutyCount": 2,
            "enforced": True,
        }


def test_workflow_fails_closed_when_explicit_responsibility_section_is_nearly_omitted(
    session_factory: sessionmaker[Session],
) -> None:
    duties = (
        "1. 主导AI Agent在内部研发平台的落地实践,探索MCP协议在工具集成与系统能力抽象中的应用;",
        "2. 基于LangChain、LangGraph、Dify等框架,构建面向研发场景的Agent应用;",
        "3. 负责Prompt工程设计与持续优化,提升Agent在复杂任务中的任务规划与执行能力;",
        "4. 主导MCP Server的设计与搭建,将现有系统能力封装为标准工具供Agent调用;",
        "5. 持续跟踪前沿AI技术,推动新技术在团队内落地;",
        "6. 与后端工程师紧密协作,完成Agent与业务系统的集成对接与数据流转设计。",
    )
    description = "\n".join(
        (
            "岗位职责",
            *duties,
            "任职要求",
            "1. 本科及以上,计算机相关专业,2年以上开发经验;",
        )
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=duties[0].removeprefix("1. "),
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=duties[0],
            confidence=0.95,
        ),
    )

    with pytest.raises(InvalidRequirementExtractorOutputError) as captured:
        _workflow(session_factory, extractor).execute(
            job_id="job_explicit_responsibility_section_coverage_loss",
            description=description,
        )

    assert "responsibility coverage too low" in str(captured.value)
    with session_factory() as session:
        trace = session.get(TraceSpanORM, captured.value.run_id)
        assert trace is not None
        assert trace.output["coverageAudit"] == {
            "dutyCandidateCount": 6,
            "coveredDutyCount": 1,
            "minimumCoveredDutyCount": 2,
            "enforced": True,
        }


def test_workflow_collapses_conjunctive_hard_sibling_into_full_harness_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = (
        "4.不要求 React / Electron / Python / 工程化四个方向都精通,"
        "但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。"
    )
    parent = "至少要能独立 owner 一个核心方向"
    child = "并能读懂、协作另一个方向。"
    description = f"任职要求：\n{evidence}\n5.熟练使用 AI Agent 工具进行真实软件开发。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=child,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.94,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_conjunctive_hard_sibling",
        description=description,
    )

    expected = evidence.removeprefix("4.").rstrip("。")
    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, expected),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {repair["strategy"] for repair in trace.output["semanticRepairs"]}
        assert "recover_uncovered_cardinality_requirement" in strategies
        assert "drop_redundant_recovered_cardinality_child" in strategies


def test_workflow_recovers_omitted_inline_hard_cardinality_segment(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = (
        "2. 了解国内外主流大模型技术,深入了解至少一个大模型体系,"
        "熟悉基于DeepSeek的微调、训练、建立智能体应用;"
    )
    description = f"岗位要求:\n{evidence}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="了解国内外主流大模型技术",
            normalized_capability="主流大模型技术",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉基于DeepSeek的微调、训练、建立智能体应用",
            normalized_capability="DeepSeek",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4281_missing_inline_cardinality",
        description=description,
    )

    assert any(
        item.type is RequirementType.CONSTRAINT
        and item.importance is RequirementImportance.MUST_HAVE
        and item.original_text == "深入了解至少一个大模型体系"
        for item in proposal.requirements
    )
    deepseek = next(
        item
        for item in proposal.requirements
        if item.original_text == "熟悉基于DeepSeek的微调、训练、建立智能体应用"
    )
    assert deepseek.importance is RequirementImportance.MUST_HAVE
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {repair["strategy"] for repair in trace.output["semanticRepairs"]}
        assert "recover_uncovered_cardinality_requirement" in strategies
        assert "preserve_post_cardinality_hard_sibling" in strategies


def test_workflow_does_not_duplicate_inline_cardinality_already_covered_by_hard_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = (
        "了解国内外主流大模型技术,深入了解至少一个大模型体系,"
        "熟悉基于DeepSeek的微调、训练、建立智能体应用"
    )
    evidence = f"2. {original};"
    description = f"岗位要求:\n{evidence}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4285_compound_cardinality_already_covered",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == [original]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "recover_uncovered_cardinality_requirement" not in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_recovers_post_cardinality_engineering_practice_sibling(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "1 精通 Python 或 Go 或 Java 至少一门语言,具备良好的工程规范和代码品味"
    description = f"二、任职要求\n3. 编程与工程能力\n{evidence}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="精通 Python 或 Go 或 Java 至少一门语言",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4286_missing_post_cardinality_engineering_practice",
        description=description,
    )

    assert any(
        item.type is RequirementType.CONSTRAINT
        and item.importance is RequirementImportance.MUST_HAVE
        and item.original_text == "具备良好的工程规范和代码品味"
        for item in proposal.requirements
    )
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "recover_post_cardinality_engineering_practice" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_does_not_recover_soft_post_cardinality_engineering_practice_sibling(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "1 精通 Python 或 Go 或 Java 至少一门语言,具备良好的工程规范和代码品味者优先"
    description = f"二、任职要求\n3. 编程与工程能力\n{evidence}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="精通 Python 或 Go 或 Java 至少一门语言",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_soft_post_cardinality_engineering_practice_not_recovered",
        description=description,
    )

    assert all(
        item.original_text != "具备良好的工程规范和代码品味者优先"
        for item in proposal.requirements
    )


def test_workflow_collapses_backend_component_capability_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    backend_line = "2 熟 悉 后 端 系 统 开 发 常 用 组 件 : MySQL/PostgreSQL 、 Redis 、 消 息 队 列"
    queue_line = "(Kafka/RabbitMQ/RocketMQ)"
    description = f"二、任职要求\n{backend_line}\n{queue_line}\n3 具备分布式系统或微服务架构的设计与实战经验"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="MySQL/PostgreSQL", normalized_capability="MySQL", importance=RequirementImportance.MUST_HAVE, evidence_span=backend_line, confidence=0.98),
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="MySQL/PostgreSQL", normalized_capability="PostgreSQL", importance=RequirementImportance.MUST_HAVE, evidence_span=backend_line, confidence=0.97),
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="Redis", normalized_capability="Redis", importance=RequirementImportance.MUST_HAVE, evidence_span=backend_line, confidence=0.96),
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="Kafka/RabbitMQ/RocketMQ", normalized_capability="Kafka", importance=RequirementImportance.MUST_HAVE, evidence_span=queue_line, confidence=0.95),
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="Kafka/RabbitMQ/RocketMQ", normalized_capability="RabbitMQ", importance=RequirementImportance.MUST_HAVE, evidence_span=queue_line, confidence=0.94),
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="Kafka/RabbitMQ/RocketMQ", normalized_capability="RocketMQ", importance=RequirementImportance.MUST_HAVE, evidence_span=queue_line, confidence=0.93),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4287_backend_component_fanout",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, "熟 悉 后 端 系 统 开 发 常 用 组 件 : MySQL/PostgreSQL 、 Redis 、 消 息 队 列"),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [repair["strategy"] for repair in trace.output["semanticRepairs"]]
        assert "recover_backend_component_umbrella" in strategies
        assert "drop_backend_component_fanout" in strategies


def test_workflow_collapses_full_line_backend_component_capability_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    backend_line = "2 熟 悉 后 端 系 统 开 发 常 用 组 件 : MySQL/PostgreSQL 、 Redis 、 消 息 队 列"
    queue_line = "(Kafka/RabbitMQ/RocketMQ)"
    description = f"二、任职要求\n{backend_line}\n{queue_line}\n3 具备分布式系统或微服务架构的设计与实战经验"
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=backend_line,
                normalized_capability=capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=backend_line,
                confidence=0.98,
            )
            for capability in ("MySQL", "PostgreSQL", "Redis", "Kafka", "RabbitMQ", "RocketMQ")
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4288_full_line_backend_component_fanout",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, "熟 悉 后 端 系 统 开 发 常 用 组 件 : MySQL/PostgreSQL 、 Redis 、 消 息 队 列"),
    ]


def test_workflow_drops_preferred_backend_component_fanout_after_umbrella_recovery(
    session_factory: sessionmaker[Session],
) -> None:
    backend_line = "2 熟 悉 后 端 系 统 开 发 常 用 组 件 : MySQL/PostgreSQL 、 Redis 、 消 息 队 列"
    queue_line = "(Kafka/RabbitMQ/RocketMQ)"
    description = f"二、任职要求\n{backend_line}\n{queue_line}\n3 具备分布式系统或微服务架构的设计与实战经验"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="MySQL/PostgreSQL", normalized_capability="MySQL", importance=RequirementImportance.MUST_HAVE, evidence_span=backend_line, confidence=0.98),
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="MySQL/PostgreSQL", normalized_capability="PostgreSQL", importance=RequirementImportance.PREFERRED, evidence_span=backend_line, confidence=0.97),
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="Redis", normalized_capability="Redis", importance=RequirementImportance.MUST_HAVE, evidence_span=backend_line, confidence=0.96),
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="Kafka/RabbitMQ/RocketMQ", normalized_capability="Kafka", importance=RequirementImportance.MUST_HAVE, evidence_span=queue_line, confidence=0.95),
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="Kafka/RabbitMQ/RocketMQ", normalized_capability="RabbitMQ", importance=RequirementImportance.PREFERRED, evidence_span=queue_line, confidence=0.94),
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="Kafka/RabbitMQ/RocketMQ", normalized_capability="RocketMQ", importance=RequirementImportance.PREFERRED, evidence_span=queue_line, confidence=0.93),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4294_backend_component_mixed_importance_fanout",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, "熟 悉 后 端 系 统 开 发 常 用 组 件 : MySQL/PostgreSQL 、 Redis 、 消 息 队 列"),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [repair["strategy"] for repair in trace.output["semanticRepairs"]]
        assert "recover_backend_component_umbrella" in strategies
        assert strategies.count("drop_backend_component_fanout") == 6


def test_workflow_collapses_backend_component_umbrella_and_queue_child(
    session_factory: sessionmaker[Session],
) -> None:
    backend_line = "2 熟 悉 后 端 系 统 开 发 常 用 组 件 : MySQL/PostgreSQL 、 Redis 、 消 息 队 列"
    queue_line = "(Kafka/RabbitMQ/RocketMQ)"
    description = f"二、任职要求\n{backend_line}\n{queue_line}\n3 具备分布式系统或微服务架构的设计与实战经验"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=backend_line,
            normalized_capability="熟悉后端系统开发常用组件",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=backend_line,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=queue_line,
            normalized_capability="消息队列",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=queue_line,
            confidence=0.97,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4289_backend_component_umbrella_queue_child",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, "熟 悉 后 端 系 统 开 发 常 用 组 件 : MySQL/PostgreSQL 、 Redis 、 消 息 队 列"),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [repair["strategy"] for repair in trace.output["semanticRepairs"]]
        assert "recover_backend_component_umbrella" in strategies
        assert strategies.count("drop_backend_component_fanout") == 2


def test_workflow_does_not_collapse_backend_components_without_live_fanout_shape(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "2 熟悉后端系统开发常用组件: MySQL/PostgreSQL、Redis、消息队列"
    description = f"二、任职要求\n{evidence}\n3 具备分布式系统或微服务架构的设计与实战经验"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(type=RequirementType.SKILL, original_text="Redis", normalized_capability="Redis", importance=RequirementImportance.MUST_HAVE, evidence_span=evidence, confidence=0.98),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_backend_component_single_skill_preserved",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.SKILL, RequirementImportance.MUST_HAVE, "Redis"),
    ]


def test_workflow_does_not_recover_soft_inline_cardinality_segment(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = (
        "2. 了解国内外主流大模型技术,深入了解至少一个大模型体系者优先,"
        "熟悉基于DeepSeek的微调、训练、建立智能体应用;"
    )
    description = f"岗位要求:\n{evidence}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="了解国内外主流大模型技术",
            normalized_capability="主流大模型技术",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉基于DeepSeek的微调、训练、建立智能体应用",
            normalized_capability="DeepSeek",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_soft_inline_cardinality_not_recovered",
        description=description,
    )

    assert all(
        item.original_text != "深入了解至少一个大模型体系者优先"
        for item in proposal.requirements
    )


def test_workflow_does_not_promote_explicitly_soft_conjunctive_sibling(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = (
        "4.至少要能独立 owner 一个核心方向,"
        "并能读懂、协作另一个方向者优先。"
    )
    parent = "至少要能独立 owner 一个核心方向"
    child = "并能读懂、协作另一个方向者优先。"
    description = f"任职要求：\n{evidence}\n5.熟练使用 Python 并完成测试验证。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=child,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.9,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_soft_conjunctive_sibling",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    assert by_text[child].importance is RequirementImportance.PREFERRED
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "preserve_conjunctive_hard_sibling" not in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_drops_redundant_parent_after_hard_skill_cardinality_split(
    session_factory: sessionmaker[Session],
) -> None:
    parent = "熟练使用Python,具备LangChain、LangGraph、Dify等至少一种Agent框架的实际项目经验;"
    skill = "熟练使用Python"
    cardinality = "具备LangChain、LangGraph、Dify等至少一种Agent框架的实际项目经验"
    description = (
        f"任职要求：\n2. {parent}\n"
        "3.熟悉Prompt工程,能独立设计结构化Prompt并完成上下文管理。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=skill,
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=skill,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=cardinality,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=cardinality,
            confidence=0.97,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=parent,
            normalized_capability="Python and Agent framework",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"2. {parent}",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_redundant_split_parent",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.SKILL, skill),
        (RequirementType.CONSTRAINT, cardinality),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_split_hard_parent" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_split_parent_when_cardinality_child_is_missing(
    session_factory: sessionmaker[Session],
) -> None:
    parent = "熟练使用Python,具备LangChain、LangGraph、Dify等至少一种Agent框架的实际项目经验;"
    skill = "熟练使用Python"
    description = (
        f"任职要求：\n2. {parent}\n"
        "3.熟悉Prompt工程,能独立设计结构化Prompt并完成上下文管理。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=skill,
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=skill,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=parent,
            normalized_capability="Python and Agent framework",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"2. {parent}",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_split_parent_missing_child",
        description=description,
    )

    assert parent in {item.original_text for item in proposal.requirements}
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_split_hard_parent" not in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_collapses_compound_domain_siblings_into_one_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "理解RAG、向量数据库、Function Calling等核心技术,能独立完成原型验证与方案评估;"
    evidence = f"4. {original}"
    description = f"任职要求：\n{evidence}\n5.具备良好的研发场景理解与快速学习能力。"
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.DOMAIN,
                original_text=original,
                normalized_capability=capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=evidence,
                confidence=0.94,
            )
            for capability in ("RAG", "向量数据库", "Function Calling")
        )
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_compound_domain_siblings",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, None, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "collapse_compound_domain_siblings" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_domain_siblings_without_compound_execution_clause(
    session_factory: sessionmaker[Session],
) -> None:
    original = "理解RAG、向量数据库、Function Calling等核心技术"
    description = (
        f"任职要求：{original}，并熟悉Prompt工程、测试验证和上线排障流程。"
    )
    extractor = StaticRequirementExtractor(
        *(
            ProposedJobRequirement(
                type=RequirementType.DOMAIN,
                original_text=original,
                normalized_capability=capability,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=original,
                confidence=0.94,
            )
            for capability in ("RAG", "向量数据库")
        )
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_plain_domain_siblings",
        description=description,
    )

    assert len(proposal.requirements) == 2
    assert all(item.type is RequirementType.DOMAIN for item in proposal.requirements)
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "collapse_compound_domain_siblings" not in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_short_numbered_scope_summary_skill_to_responsibility(
    session_factory: sessionmaker[Session],
) -> None:
    summary = "企业级AI与智能体应用开发"
    summary_evidence = "2、企业级AI与智能体应用开发 薪酬open"
    duties = (
        "1.深入汽车制造与供应链场景,挖掘高价值AI应用机会,设计落地路径。",
        "2.主导企业级AI应用与智能体系统设计开发,构建可复用AI能力中台。",
        "3.协同业务部门推进AI场景试点与规模化推广,实现效率提升。",
        "4.制定AI工程标准与规范,推动敏捷交付与持续集成。",
    )
    description = "\n".join((summary_evidence, *duties, "任职要求", "本科及以上学历。"))
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=summary,
            normalized_capability=summary,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=summary_evidence,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.RESPONSIBILITY,
                original_text=duty,
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=duty,
                confidence=0.95,
            )
            for duty in duties
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_short_scope_summary_skill_drift",
        description=description,
    )

    assert proposal.requirements[0].type is RequirementType.RESPONSIBILITY
    assert proposal.requirements[0].normalized_capability is None
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "short_scope_summary_responsibility" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_drops_redundant_short_scope_summary_responsibility(
    session_factory: sessionmaker[Session],
) -> None:
    summary = "企业级AI与智能体应用开发"
    summary_evidence = "2、企业级AI与智能体应用开发 薪酬open"
    duties = (
        "1.深入汽车制造与供应链场景,挖掘高价值AI应用机会,设计落地路径。",
        "2.主导企业级AI应用与智能体系统设计开发,构建可复用AI能力中台。",
        "3.协同业务部门推进AI场景试点与规模化推广,实现效率提升。",
        "4.制定AI工程标准与规范,推动敏捷交付与持续集成。",
    )
    description = "\n".join((summary_evidence, *duties, "任职要求", "本科及以上学历。"))
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=summary,
            normalized_capability="AI Application Development",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=summary_evidence,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.RESPONSIBILITY,
                original_text=duty,
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=duty,
                confidence=0.95,
            )
            for duty in duties
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_redundant_short_scope_summary_responsibility",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == list(duties)
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_short_scope_summary_responsibility" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_short_action_responsibility_before_detailed_duties(
    session_factory: sessionmaker[Session],
) -> None:
    summary = "负责AI平台开发"
    summary_evidence = "2、负责AI平台开发"
    duties = (
        "1.深入汽车制造与供应链场景,挖掘高价值AI应用机会,设计落地路径。",
        "2.主导企业级AI应用与智能体系统设计开发,构建可复用AI能力中台。",
        "3.协同业务部门推进AI场景试点与规模化推广,实现效率提升。",
    )
    description = "\n".join((summary_evidence, *duties, "任职要求", "本科及以上学历。"))
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=summary,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=summary_evidence,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.RESPONSIBILITY,
                original_text=duty,
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=duty,
                confidence=0.95,
            )
            for duty in duties
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_short_action_responsibility",
        description=description,
    )

    assert proposal.requirements[0].original_text == summary
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_short_scope_summary_responsibility" not in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_explicit_hard_skill_even_before_responsibility_block(
    session_factory: sessionmaker[Session],
) -> None:
    skill = "熟练使用Python"
    skill_evidence = "2、熟练使用Python"
    duties = (
        "1.主导AI应用方案设计与落地,推动业务场景持续优化。",
        "2.负责Agent工具集成与服务治理,提升系统稳定性。",
        "3.协同业务团队推进试点上线,跟踪应用效果与改进项。",
        "4.制定工程规范与测试流程,推动持续集成与交付。",
    )
    description = "\n".join((skill_evidence, *duties, "任职要求", "本科及以上学历。"))
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=skill,
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=skill_evidence,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.RESPONSIBILITY,
                original_text=duty,
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=duty,
                confidence=0.95,
            )
            for duty in duties
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_explicit_skill_before_duties",
        description=description,
    )

    assert proposal.requirements[0].type is RequirementType.SKILL
    assert proposal.requirements[0].normalized_capability == "Python"
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "short_scope_summary_responsibility" not in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_short_skill_when_scope_summary_context_is_incomplete(
    session_factory: sessionmaker[Session],
) -> None:
    summary = "企业级AI与智能体应用开发"
    summary_evidence = "2、企业级AI与智能体应用开发"
    duties = (
        "1.主导AI应用方案设计与落地,推动业务场景持续优化。",
        "2.负责Agent工具集成与服务治理,提升系统稳定性。",
    )
    description = "\n".join((summary_evidence, *duties, "任职要求", "本科及以上学历,熟悉Python。"))
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=summary,
            normalized_capability=summary,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=summary_evidence,
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.RESPONSIBILITY,
                original_text=duty,
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=duty,
                confidence=0.95,
            )
            for duty in duties
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_incomplete_scope_summary_context",
        description=description,
    )

    assert proposal.requirements[0].type is RequirementType.SKILL
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "short_scope_summary_responsibility" not in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_explicit_soft_only_must_have_and_deduplicates_it(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = (
        "3.熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等),"
        "有落地项目经验者优先。"
    )
    soft = "有落地项目经验者优先"
    description = f"任职要求\n{evidence}\n4.优秀的跨部门沟通与业务理解能力,能快速定位痛点并设计技术方案。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=soft,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=soft,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=soft,
            normalized_capability="智能体落地项目经验",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_explicit_soft_only_conflict",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text, item.evidence_span) for item in proposal.requirements] == [
        (RequirementType.EXPERIENCE, RequirementImportance.PREFERRED, soft, soft),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {repair["strategy"] for repair in trace.output["semanticRepairs"]}
        assert "explicit_soft_marker_preferred" in strategies
        assert "drop_exact_duplicate_requirement" in strategies


def test_workflow_inherits_numbered_annotated_bonus_section_importance(
    session_factory: sessionmaker[Session],
) -> None:
    gateway = "有 AI 网关 / API 网关 研发经验(如 Kong、APISIX、Envoy 插件开发或自研网关)"
    orchestration = "有 多模型编排与融合调度 相关项目经验(模型灰度、A/B 测试、Fallback 策略)"
    inference = "熟悉 vLLM / TGI / Triton Inference Server 等推理引擎"
    cuda = "有 CUDA 编程或模型推理优化经验"
    description = (
        "二、任职要求\n"
        "熟练使用 Python。\n"
        "三、加分项(满足越多越优先)\n"
        f"1. {gateway}\n"
        f"2. {orchestration}\n"
        f"3. {inference}\n"
        f"4. {cuda}\n"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=gateway,
            normalized_capability="API Gateway",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"1. {gateway}",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=orchestration,
            normalized_capability="Multi-Model Orchestration",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"2. {orchestration}",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=inference,
            normalized_capability="vLLM",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"3. {inference}",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=cuda,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"4. {cuda}",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4251_numbered_annotated_bonus_section",
        description=description,
    )

    assert [item.importance for item in proposal.requirements] == [
        RequirementImportance.BONUS,
        RequirementImportance.BONUS,
        RequirementImportance.BONUS,
        RequirementImportance.BONUS,
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert [item["strategy"] for item in trace.output["semanticRepairs"]].count(
            "explicit_bonus_section"
        ) == 4


def test_workflow_inherits_explicit_bonus_section_importance_without_leaking_past_next_section(
    session_factory: sessionmaker[Session],
) -> None:
    mcp_skill = "熟悉MCP协议的设计理念和实现细节"
    mcp_experience = "有实际的协议实现或集成经验"
    writing_experience = "有AI相关的技术论文发表或高质量技术博客输出"
    duty = "负责平台稳定性治理和线上问题排查"
    description = (
        "任职要求:\n"
        "深厚的Python功底,能够独立调试和优化复杂的第三方开源项目。\n"
        "加分项:\n"
        f"MCP协议深度实践: {mcp_skill},{mcp_experience}。\n"
        f"论文与技术博客: {writing_experience},展现深度的技术思考能力。\n"
        "岗位职责:\n"
        f"{duty}。\n"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=mcp_skill,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=mcp_skill,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=mcp_experience,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=mcp_experience,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=writing_experience,
            normalized_capability="Technical Writing",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=writing_experience,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=duty,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=duty,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_explicit_bonus_section_importance",
        description=description,
    )

    assert [item.importance for item in proposal.requirements[:3]] == [
        RequirementImportance.BONUS,
        RequirementImportance.BONUS,
        RequirementImportance.BONUS,
    ]
    assert proposal.requirements[3].importance is RequirementImportance.MUST_HAVE
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [repair["strategy"] for repair in trace.output["semanticRepairs"]]
        assert strategies.count("explicit_bonus_section") == 3


def test_workflow_collapses_live_harness_cardinality_fragments_and_direction_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    group_line = "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    direction_line = "【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。"
    combination_line = (
        "4.不要求 React / Electron / Python / 工程化四个方向都精通,"
        "但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。"
    )
    description = (
        "任职要求\n"
        f"{group_line}\n"
        f"{direction_line}\n"
        f"{combination_line}\n"
        "5.熟练使用 AI Agent 工具进行真实软件开发。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="工程能力扎实",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=group_line,
            confidence=0.96,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="至少在以下一个方向非常熟练(会其中一个方向即可)",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=group_line,
            confidence=0.96,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="React",
            normalized_capability="React",
            importance=RequirementImportance.PREFERRED,
            evidence_span=direction_line,
            confidence=0.94,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="TypeScript",
            normalized_capability="TypeScript",
            importance=RequirementImportance.PREFERRED,
            evidence_span=direction_line,
            confidence=0.94,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="不要求 React / Electron / Python / 工程化四个方向都精通",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=combination_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="至少要能独立 owner 一个核心方向",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=combination_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text="并能读懂、协作另一个方向",
            normalized_capability="协作另一个方向",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=combination_line,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4265_harness_cardinality_fanout",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text, item.normalized_capability) for item in proposal.requirements] == [
        (
            RequirementType.CONSTRAINT,
            RequirementImportance.MUST_HAVE,
            "工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):",
            None,
        ),
        (
            RequirementType.SKILL,
            RequirementImportance.PREFERRED,
            direction_line,
            "React",
        ),
        (
            RequirementType.CONSTRAINT,
            RequirementImportance.MUST_HAVE,
            "不要求 React / Electron / Python / 工程化四个方向都精通,但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向",
            None,
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {repair["strategy"] for repair in trace.output["semanticRepairs"]}
        assert "collapse_cardinality_requirement_line" in strategies
        assert "collapse_alternative_group_child_siblings" in strategies


def test_workflow_collapses_live_harness_mixed_full_line_and_body_direction_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    group_line = "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    direction_line = "【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。"
    direction_body = "React、TypeScript、状态管理、复杂交互、桌面端 UI 工程"
    description = (
        "【任职要求】\n"
        f"{group_line}\n"
        f"{direction_line}\n"
        "【桌面端方向】:Electron、主进程/渲染进程通信、本地文件系统、进程管理、跨平台桌面应用。\n"
        "【后端方向】:Python、异步/进程模型、工具系统、服务端架构、测试与工程化。\n"
        "【工程化/代码控制方向】:Git、branch/worktree、diff/patch、merge/rebase、冲突处理、代码变更追踪、rollback/restore、CI/测试流水线。\n"
        "4.不要求 React / Electron / Python / 工程化四个方向都精通,但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。\n"
    )
    desktop_line = "【桌面端方向】:Electron、主进程/渲染进程通信、本地文件系统、进程管理、跨平台桌面应用。"
    backend_line = "【后端方向】:Python、异步/进程模型、工具系统、服务端架构、测试与工程化。"
    engineering_line = "【工程化/代码控制方向】:Git、branch/worktree、diff/patch、merge/rebase、冲突处理、代码变更追踪、rollback/restore、CI/测试流水线。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可)",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=group_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=direction_line,
            normalized_capability="React",
            importance=RequirementImportance.PREFERRED,
            evidence_span=direction_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=direction_body,
            normalized_capability="TypeScript",
            importance=RequirementImportance.PREFERRED,
            evidence_span=direction_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=desktop_line,
            normalized_capability="Electron",
            importance=RequirementImportance.PREFERRED,
            evidence_span=desktop_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=backend_line,
            normalized_capability="Python",
            importance=RequirementImportance.PREFERRED,
            evidence_span=backend_line,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=engineering_line,
            normalized_capability="Git",
            importance=RequirementImportance.PREFERRED,
            evidence_span=engineering_line,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4290_harness_mixed_direction_fanout",
        description=description,
    )

    direction_items = [
        item
        for item in proposal.requirements
        if item.evidence_span == direction_line
    ]
    assert [
        (item.type, item.importance, item.original_text, item.normalized_capability)
        for item in direction_items
    ] == [
        (
            RequirementType.SKILL,
            RequirementImportance.PREFERRED,
            direction_line,
            "React",
        )
    ]


def test_workflow_recovers_bracketed_requirement_cardinality_parent_from_live_partial_fragments(
    session_factory: sessionmaker[Session],
) -> None:
    full = (
        "不要求 React / Electron / Python / 工程化四个方向都精通,"
        "但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向"
    )
    evidence = f"4.{full}。"
    description = (
        "【任职要求】\n"
        "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):\n"
        "【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。\n"
        f"{evidence}\n"
        "5.熟练使用 AI Agent 工具进行真实软件开发。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="至少要能独立 owner 一个核心方向",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="并能读懂、协作另一个方向",
            normalized_capability="Cross-Direction Collaboration",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4267_bracketed_cardinality_partial_fragments",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            RequirementImportance.MUST_HAVE,
            full,
            None,
        )
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = [item["strategy"] for item in trace.output["semanticRepairs"]]
        assert "recover_uncovered_cardinality_requirement" in strategies
        assert strategies.count("drop_redundant_recovered_cardinality_child") == 2


def test_workflow_recovers_uncovered_requirement_section_cardinality_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    group_header = "工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    missing = (
        "不要求 React / Electron / Python / 工程化四个方向都精通,"
        "但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。"
    )
    missing_evidence = f"4.{missing}"
    description = (
        "任职要求\n"
        f"3.{group_header}\n"
        "【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。\n"
        "【桌面端方向】:Electron、主进程/渲染进程通信、本地文件系统、进程管理、跨平台桌面应用。\n"
        "【后端方向】:Python、异步/进程模型、工具系统、服务端架构、测试与工程化。\n"
        "【工程化/代码控制方向】:Git、branch/worktree、diff/patch、merge/rebase、冲突处理、代码变更追踪、rollback/restore、CI/测试流水线。\n"
        f"{missing_evidence}\n"
        "5.熟练使用 AI Agent 工具进行真实软件开发,对 Agent 产品有高强度使用经验。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=group_header,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"3.{group_header}",
            confidence=0.95,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.SKILL,
                original_text=direction,
                normalized_capability=capability,
                importance=RequirementImportance.PREFERRED,
                evidence_span=direction,
                confidence=0.9,
            )
            for direction, capability in (
                ("【前端方向】:React、TypeScript、状态管理、复杂交互、桌面端 UI 工程。", "React"),
                ("【桌面端方向】:Electron、主进程/渲染进程通信、本地文件系统、进程管理、跨平台桌面应用。", "Electron"),
                ("【后端方向】:Python、异步/进程模型、工具系统、服务端架构、测试与工程化。", "Python"),
                ("【工程化/代码控制方向】:Git、branch/worktree、diff/patch、merge/rebase、冲突处理、代码变更追踪、rollback/restore、CI/测试流水线。", "Git"),
            )
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_uncovered_cardinality_requirement",
        description=description,
    )

    recovered_text = missing.rstrip("。")
    recovered = [item for item in proposal.requirements if item.original_text == recovered_text]
    assert len(recovered) == 1
    assert recovered[0].type is RequirementType.CONSTRAINT
    assert recovered[0].importance is RequirementImportance.MUST_HAVE
    assert recovered[0].evidence_span == missing_evidence
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "recover_uncovered_cardinality_requirement" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_drops_redundant_requirement_section_responsibility_children(
    session_factory: sessionmaker[Session],
) -> None:
    parent = "熟悉Prompt工程,能独立设计结构化Prompt,具备上下文管理与复杂意图拆解能力"
    evidence = f"3. {parent};"
    child_one = "能独立设计结构化Prompt"
    child_two = "具备上下文管理与复杂意图拆解能力"
    description = (
        "任职要求\n"
        f"{evidence}\n"
        "4. 理解RAG、向量数据库、Function Calling等核心技术,能独立完成原型验证与方案评估;\n"
        "5. 具备良好的研发场景理解与快速学习能力,能将业务需求转化为可落地的Agent方案;"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=child_one,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.96,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=child_two,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_redundant_qualification_responsibility_children",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, parent),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_qualification_responsibility_child" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_abstract_ability_experience_drift_to_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "工程能力扎实"
    evidence = "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    description = f"任职要求\n{evidence}\n4.熟练使用 AI Agent 工具进行真实软件开发。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_abstract_ability_experience_drift",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    assert by_text[original].type is RequirementType.CONSTRAINT
    assert by_text[original].normalized_capability is None
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "abstract_evaluative_type_constraint" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_replaces_partial_harness_cardinality_children_with_full_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    full = (
        "不要求 React / Electron / Python / 工程化四个方向都精通,"
        "但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。"
    )
    evidence = f"4.{full}"
    partial = "但至少要能独立 owner 一个核心方向"
    conjunctive = "并能读懂、协作另一个方向"
    description = f"任职要求\n{evidence}\n5.熟练使用 AI Agent 工具进行真实软件开发。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=partial,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=conjunctive,
            normalized_capability="读懂协作另一个方向",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_partial_harness_cardinality_children",
        description=description,
    )

    expected = full.rstrip("。")
    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, expected),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {repair["strategy"] for repair in trace.output["semanticRepairs"]}
        assert "recover_uncovered_cardinality_requirement" in strategies
        assert "drop_redundant_recovered_cardinality_child" in strategies


def test_workflow_normalizes_hard_skill_capability_before_explicit_soft_suffix(
    session_factory: sessionmaker[Session],
) -> None:
    hard = "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    soft = "有落地项目经验者优先"
    evidence = f"3.{hard},{soft}。"
    description = f"任职要求\n{evidence}\n4.优秀的跨部门沟通与业务理解能力,能快速定位痛点并设计技术方案。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=hard,
            normalized_capability="熟悉智能体技术栈且有落地项目经验",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=hard,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=soft,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=soft,
            confidence=0.98,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_hard_skill_capability_soft_scope",
        description=description,
    )

    hard_item = next(item for item in proposal.requirements if item.original_text == hard)
    assert hard_item.normalized_capability == "智能体(Agent)技术栈"
    assert hard_item.importance is RequirementImportance.MUST_HAVE
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }
        assert "normalize_hard_skill_capability_before_soft_suffix" in strategies
        assert "normalize_umbrella_skill_example_capability" in strategies


def test_workflow_drops_same_evidence_constraint_subclause_under_full_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "6. 有英文读写能力,了解国外前沿产品网站和文档,具备国际化视角;"
    parent = "有英文读写能力,了解国外前沿产品网站和文档,具备国际化视角"
    child = "了解国外前沿产品网站和文档,具备国际化视角"
    description = f"岗位要求:\n{evidence}\n7.具有较强的沟通、表达和总结能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=child,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4282_constraint_subclause_duplicate",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, parent),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_qualification_subclause" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_preserves_constraint_subclause_from_different_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    parent_evidence = "6. 有英文读写能力,了解国外前沿产品网站和文档,具备国际化视角;"
    child_evidence = "7. 了解国外前沿产品网站和文档,具备国际化视角;"
    parent = "有英文读写能力,了解国外前沿产品网站和文档,具备国际化视角"
    child = "了解国外前沿产品网站和文档,具备国际化视角"
    description = f"岗位要求:\n{parent_evidence}\n{child_evidence}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=child,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=child_evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_constraint_subclause_different_evidence",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, parent),
        (RequirementType.CONSTRAINT, child),
    ]


def test_workflow_drops_domain_subclause_covered_by_full_requirement_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    parent = (
        "6.理解 LLM / Agent 的基本机制,包括 LLM API、context window、agent loop、"
        "tool use、reasoning、planning、MCP、memory、subagent 等。"
    )
    child = "理解 LLM / Agent 的基本机制"
    description = f"任职要求\n{parent}\n7.有良好的工程习惯,重视可维护性、测试、可观测性和安全边界。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=child,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_redundant_domain_qualification_subclause",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, parent),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_qualification_subclause" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_drops_same_evidence_education_subclause_under_full_education_parent(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "1.本科及以上学历,计算机、人工智能或汽车工程等相关专业,8年以上AI产品/解决方案经验。"
    parent = "本科及以上学历,计算机、人工智能或汽车工程等相关专业"
    child = "计算机、人工智能或汽车工程等相关专业"
    description = f"任职要求\n{evidence}\n2.精通AI常见场景并具备企业级系统架构设计能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=parent,
            normalized_capability="本科及以上学历",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=child,
            normalized_capability="计算机相关专业",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4272_education_subclause_duplicate",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.EDUCATION, parent),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_qualification_subclause" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_drops_same_evidence_education_subclause_without_explicit_requirement_heading(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "1.本科及以上学历,计算机、人工智能或汽车工程等相关专业,8年以上AI产品/解决方案经验。"
    parent = "本科及以上学历,计算机、人工智能或汽车工程等相关专业"
    child = "计算机、人工智能或汽车工程等相关专业"
    description = f"6.探索智能体平台。\n{evidence}\n2.精通AI常见场景。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=parent,
            normalized_capability="本科及以上学历",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=child,
            normalized_capability="计算机、人工智能或汽车工程等相关专业",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4280_education_subclause_duplicate_no_heading",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.EDUCATION, parent),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_qualification_subclause" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_preserves_same_evidence_cross_type_subclause_without_requirement_heading(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "本科及以上学历,计算机相关专业,具备系统架构设计能力。"
    parent = "本科及以上学历,计算机相关专业"
    child = "具备系统架构设计能力"
    description = f"岗位说明\n负责平台建设与持续交付。\n{evidence}\n支持跨团队协作与长期演进。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=parent,
            normalized_capability="本科及以上学历",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=child,
            normalized_capability="系统架构设计能力",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_no_heading_cross_type_qualification_subclause",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.EDUCATION, parent),
        (RequirementType.DOMAIN, child),
    ]


def test_workflow_drops_same_source_nonexperience_experience_subclause_under_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "2.精通AI常见场景(如预测、决策、NLP、CV等),具备企业级AI系统架构设计能力。"
    parent = "精通AI常见场景(如预测、决策、NLP、CV等),具备企业级AI系统架构设计能力"
    child = "具备企业级AI系统架构设计能力"
    description = f"任职要求\n{evidence}\n3.熟悉智能体技术栈。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=child,
            normalized_capability="企业级AI系统架构设计能力",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4273_nonexperience_experience_subclause",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, parent),
    ]


def test_workflow_keeps_true_experience_subclause_even_when_same_source_constraint_exists(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "具备企业级系统架构设计能力,有3年以上AI系统架构设计经验"
    parent = evidence
    child = "有3年以上AI系统架构设计经验"
    description = f"任职要求\n{evidence}。\n同时需要参与需求分析、方案评审、测试验证、上线交付和线上问题排查。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=child,
            normalized_capability="AI系统架构设计经验",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_true_experience_subclause_preserved",
        description=description,
    )

    assert [item.original_text for item in proposal.requirements] == [parent, child]


def test_workflow_normalizes_evaluative_qualification_responsibility_to_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "优秀的跨部门沟通与业务理解能力,能快速定位痛点并设计技术方案。"
    description = (
        f"{original}\n"
        "5.有成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径者优先。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_evaluative_qualification_cross_type_duplicate",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {repair["strategy"] for repair in trace.output["semanticRepairs"]}
        assert "abstract_evaluative_type_constraint" in strategies
        assert "drop_exact_duplicate_requirement" in strategies


def test_workflow_drops_exact_non_skill_duplicate_even_when_provider_capability_differs(
    session_factory: sessionmaker[Session],
) -> None:
    original = "需要有车端经验"
    description = (
        f"任职要求：{original}，并具备良好的系统问题分析能力。"
        "同时需要能够与产品和研发团队协作推进复杂项目落地。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability="车端经验",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_exact_experience_duplicate_capability_drift",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.EXPERIENCE, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_exact_duplicate_requirement" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_drops_exact_education_duplicate_when_provider_capability_differs(
    session_factory: sessionmaker[Session],
) -> None:
    original = "计算机科学、人工智能等相关专业本科及以上学历"
    evidence = f"1. {original},5年以上工作经验,精通toB/G解决方案设计;"
    description = f"任职要求\n{evidence}\n2. 了解国内外主流大模型技术。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=original,
            normalized_capability="计算机科学",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=original,
            normalized_capability="人工智能",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4259_education_capability_duplicate",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.EDUCATION, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_exact_duplicate_requirement" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_drops_redundant_same_source_constraint_subclause_from_human_reject_case(
    session_factory: sessionmaker[Session],
) -> None:
    parent = "有英文读写能力,了解国外前沿产品网站和文档,具备国际化视角"
    child = "了解国外前沿产品网站和文档,具备国际化视角"
    evidence = f"6. {parent};"
    description = f"岗位要求:\n{evidence}\n7. 具有较强的沟通、表达、总结及文档制作能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=child,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4295_same_source_constraint_subclause",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, parent),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_same_source_constraint_subclause" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_collapses_hard_compound_ability_capability_fanout_from_human_reject_case(
    session_factory: sessionmaker[Session],
) -> None:
    original = "有较强的系统问题分析经验和抽象设计能力,能够解决复杂的系统问题"
    evidence = f"4、{original};"
    description = f"任职要求:\n{evidence}\n5、有车载应用开发经验者优先。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="系统问题分析",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="抽象设计",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.97,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="能够解决复杂的系统问题",
            normalized_capability="系统问题解决",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4295_compound_ability_fanout",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "collapse_hard_compound_ability_fanout" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_collapses_same_text_hard_inline_alternative_capability_fanout_from_human_reject_case(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟练使用 PyTorch/TensorFlow。"
    evidence = (
        "2、核心技能:精通 Python,熟练使用 PyTorch/TensorFlow。"
        "精通 LangChain、LlamaIndex 等大模型应用开发框架。"
    )
    description = f"任职要求:\n{evidence}\n3、加分项:懂提示词工程优化。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="PyTorch",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="TensorFlow",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.97,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4295_inline_alternative_fanout",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text, item.normalized_capability) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, original, None),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "collapse_hard_inline_alternative_capability_fanout" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_collapses_recursive_hard_skill_subset_chain_from_formal_case_16(
    session_factory: sessionmaker[Session],
) -> None:
    parent = "熟练掌握大模型 API 调用、RAG 检索增强和 Agent 编排框架"
    middle = "熟练掌握大模型 API 调用、RAG 检索增强"
    child = "熟练掌握大模型 API 调用"
    evidence = f"2. 硬核工程能力：{parent}，并具备受限网络部署经验。"
    description = f"任职要求\n{evidence}\n3. 具备良好的沟通协作能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=parent,
            normalized_capability="Agent 编排框架",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=middle,
            normalized_capability="RAG",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.97,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=child,
            normalized_capability="大模型 API",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_formal_case_16_recursive_hard_skill_subset_chain",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, parent, None),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "collapse_recursive_hard_skill_subset_chain" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_collapses_formal_case_20_bonus_umbrella_capability_fanout(
    session_factory: sessionmaker[Session],
) -> None:
    parent = "5、加分项:熟悉 MCP 协议、LangChain、AutoGPT、LlamaIndex 等 Agent 开发框架。"
    evidence = parent
    description = f"任职要求\n4、技术能力:熟悉主流大模型技术架构。\n{parent}\n"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉 MCP 协议",
            normalized_capability="MCP",
            importance=RequirementImportance.BONUS,
            evidence_span=evidence,
            confidence=0.99,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=parent,
            normalized_capability="LangChain",
            importance=RequirementImportance.BONUS,
            evidence_span=evidence,
            confidence=0.99,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="AutoGPT",
            normalized_capability="AutoGPT",
            importance=RequirementImportance.BONUS,
            evidence_span=evidence,
            confidence=0.99,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="LlamaIndex",
            normalized_capability="LlamaIndex",
            importance=RequirementImportance.BONUS,
            evidence_span=evidence,
            confidence=0.99,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_formal_case_20_bonus_umbrella_capability_fanout",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text, item.normalized_capability)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, RequirementImportance.BONUS, parent, None),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "collapse_bonus_umbrella_capability_fanout" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_keeps_explicit_independent_bonus_capabilities_without_umbrella(
    session_factory: sessionmaker[Session],
) -> None:
    evidence = "5、加分项:熟悉 MCP 协议、LangChain、AutoGPT。"
    description = f"任职要求\n4、技术能力:熟悉主流大模型技术架构。\n{evidence}\n"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟悉 MCP 协议",
            normalized_capability="MCP",
            importance=RequirementImportance.BONUS,
            evidence_span=evidence,
            confidence=0.99,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="LangChain",
            normalized_capability="LangChain",
            importance=RequirementImportance.BONUS,
            evidence_span=evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="AutoGPT",
            normalized_capability="AutoGPT",
            importance=RequirementImportance.BONUS,
            evidence_span=evidence,
            confidence=0.97,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_independent_bonus_capabilities_without_umbrella",
        description=description,
    )

    assert [item.normalized_capability for item in proposal.requirements] == [
        "MCP",
        "LangChain",
        "AutoGPT",
    ]


def test_workflow_keeps_three_explicit_hard_technical_capabilities_from_same_source(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉模型训练、推理优化和模型部署"
    description = f"任职要求\n1. {original}。\n2. 具备良好的工程实践能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="模型训练",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="推理优化",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.97,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="模型部署",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_three_explicit_hard_technical_capabilities",
        description=description,
    )

    assert [item.normalized_capability for item in proposal.requirements] == [
        "模型训练",
        "推理优化",
        "模型部署",
    ]


def test_workflow_keeps_distinct_same_source_constraint_siblings_without_parent_child_overlap(
    session_factory: sessionmaker[Session],
) -> None:
    first = "有英文读写能力"
    second = "具备国际化视角"
    evidence = "6. 有英文读写能力,了解国外前沿产品网站和文档,具备国际化视角;"
    description = f"岗位要求:\n{evidence}\n7. 具有较强的沟通表达能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=first,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=second,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_same_source_distinct_constraint_siblings",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, first),
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, second),
    ]


def test_workflow_keeps_distinct_education_requirements_with_different_source_facts(
    session_factory: sessionmaker[Session],
) -> None:
    first = "本科及以上学历"
    second = "计算机相关专业"
    description = (
        f"任职要求\n1.{first}\n2.{second}\n"
        "3.熟练使用Python并具备服务开发、测试、持续交付和线上问题排查能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=first,
            normalized_capability="本科",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"1.{first}",
            confidence=0.99,
        ),
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=second,
            normalized_capability="计算机",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"2.{second}",
            confidence=0.99,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_distinct_education_facts_not_deduped",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.EDUCATION, first),
        (RequirementType.EDUCATION, second),
    ]


def test_workflow_drops_duplicate_experience_across_repeated_source_occurrences_and_wider_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    original = "需要有车端经验"
    first_evidence = "需要有车端经验,非车端经验的无法到副总师的层级"
    second_evidence = "5.有成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径者优先。 需要有车端经验,非车端经验的无法到副总师的层级"
    description = f"任职要求：{first_evidence}\n{second_evidence}"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=first_evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=second_evidence,
            confidence=0.96,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_repeated_experience_wider_evidence",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.EXPERIENCE, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_exact_duplicate_requirement" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_splits_numbered_hard_tool_usage_from_product_experience(
    session_factory: sessionmaker[Session],
) -> None:
    original = "5.熟练使用 AI Agent 工具进行真实软件开发,对 Agent 产品有高强度使用经验。"
    description = (
        f"任职要求\n{original}\n"
        "6.理解 LLM / Agent 的基本机制,包括 LLM API、context window、agent loop、tool use。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=original,
            normalized_capability="AI Agent tools",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_numbered_fused_tool_usage_product_experience",
        description=description,
    )

    assert [(item.type, item.importance, item.original_text) for item in proposal.requirements] == [
        (
            RequirementType.CONSTRAINT,
            RequirementImportance.MUST_HAVE,
            "5.熟练使用 AI Agent 工具进行真实软件开发",
        ),
        (
            RequirementType.EXPERIENCE,
            RequirementImportance.MUST_HAVE,
            "对 Agent 产品有高强度使用经验",
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "split_skill_experience" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_compound_qualification_experience_drift(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉Prompt工程,能独立设计结构化Prompt,具备上下文管理与复杂意图拆解能力;"
    evidence = f"3. {original}"
    description = (
        f"任职要求\n{evidence}\n"
        "4. 理解RAG、向量数据库、Function Calling等核心技术,能独立完成原型验证与方案评估;"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_compound_qualification_experience_drift",
        description=description,
    )

    assert [(item.type, item.normalized_capability, item.importance, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, None, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "non_experience_qualification_constraint" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_core_technology_compound_experience_drift_to_constraint(
    session_factory: sessionmaker[Session],
) -> None:
    original = "理解RAG、向量数据库、Function Calling等核心技术,能独立完成原型验证与方案评估"
    evidence = f"4. {original};"
    description = (
        "任职要求\n"
        f"{evidence}\n"
        "5. 具备良好的研发场景理解与快速学习能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_live_v4248_core_technology_experience_drift",
        description=description,
    )

    assert [
        (item.type, item.normalized_capability, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.CONSTRAINT,
            None,
            RequirementImportance.MUST_HAVE,
            original,
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "non_experience_qualification_constraint" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_drops_headingless_evaluative_qualification_responsibility_child(
    session_factory: sessionmaker[Session],
) -> None:
    parent = "优秀的跨部门沟通与业务理解能力,能快速定位痛点并设计技术方案"
    parent_evidence = parent
    child = "能快速定位痛点并设计技术方案"
    child_evidence = f"4.{parent}。"
    description = (
        f"{child_evidence}\n"
        "5.有成功主导千万级以上AI项目的经验,熟悉车企数字化转型路径者优先。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=parent_evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=child,
            normalized_capability="problem identification and solution design",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=child_evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_headingless_evaluative_qualification_child",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, parent),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_qualification_responsibility_child" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_drops_redundant_cardinality_marker_fragment(
    session_factory: sessionmaker[Session],
) -> None:
    parent = "工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):"
    evidence = f"3.{parent}"
    description = f"任职要求\n{evidence}\n4.熟练使用 AI Agent 工具进行真实软件开发。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=parent,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="至少",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=evidence,
            confidence=0.7,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_redundant_cardinality_marker_fragment",
        description=description,
    )

    assert [(item.type, item.original_text) for item in proposal.requirements] == [
        (RequirementType.CONSTRAINT, parent),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "drop_redundant_cardinality_fragment" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_collapses_numbering_equivalent_hard_duplicates(
    session_factory: sessionmaker[Session],
) -> None:
    education = "本科及以上,计算机相关专业"
    python_skill = "熟练使用Python"
    qualification = "具备良好的研发场景理解与快速学习能力,能将业务需求转化为可落地的Agent方案"
    description = (
        "任职要求\n"
        f"1. {education},2年以上开发经验,有LLM/Agent应用落地项目经验;\n"
        f"2. {python_skill},具备LangChain、LangGraph、Dify等至少一种Agent框架的实际项目经验;\n"
        f"5. {qualification};"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=education,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"1. {education},2年以上开发经验,有LLM/Agent应用落地项目经验;",
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.EDUCATION,
            original_text=f"1. {education}",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"1. {education}",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=python_skill,
            normalized_capability="Python",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"2. {python_skill},具备LangChain、LangGraph、Dify等至少一种Agent框架的实际项目经验;",
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=f"2. {python_skill}",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"2. {python_skill}",
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=qualification,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=qualification,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=f"5. {qualification};",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=f"5. {qualification};",
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_numbering_equivalent_hard_duplicates",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.EDUCATION, RequirementImportance.MUST_HAVE, education),
        (RequirementType.SKILL, RequirementImportance.MUST_HAVE, python_skill),
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, qualification),
    ]


def test_workflow_promotes_hard_skill_prefix_before_explicit_soft_sibling(
    session_factory: sessionmaker[Session],
) -> None:
    hard = "熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)"
    soft = "有落地项目经验者优先"
    evidence = f"3.{hard},{soft}。"
    description = f"任职要求\n{evidence}\n4.优秀的跨部门沟通与业务理解能力。"
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=hard,
            normalized_capability="Agent technology stack",
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=soft,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_hard_skill_prefix_before_soft_sibling",
        description=description,
    )

    by_text = {item.original_text: item for item in proposal.requirements}
    assert by_text[hard].type is RequirementType.SKILL
    assert by_text[hard].importance is RequirementImportance.MUST_HAVE
    assert by_text[soft].importance is RequirementImportance.PREFERRED
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "promote_hard_skill_prefix_before_soft_sibling" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_explicit_requirement_section_qualification_types(
    session_factory: sessionmaker[Session],
) -> None:
    prompt_requirement = "3. 熟悉Prompt工程,能独立设计结构化Prompt,具备上下文管理与复杂意图拆解能力;"
    rag_requirement = "4. 理解RAG、向量数据库、Function Calling等核心技术,能独立完成原型验证与方案评估;"
    scenario_requirement = "5. 具备良好的研发场景理解与快速学习能力,能将业务需求转化为可落地的Agent方案;"
    description = "\n".join(
        (
            "任职要求",
            prompt_requirement,
            rag_requirement,
            scenario_requirement,
            "6. 有MCP协议实践、研发效能/DevOps工具链经验者优先。",
        )
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=prompt_requirement,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=prompt_requirement,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=rag_requirement,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=rag_requirement,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=scenario_requirement,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=scenario_requirement,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_explicit_requirement_section_type_drift",
        description=description,
    )

    assert [item.type for item in proposal.requirements] == [
        RequirementType.CONSTRAINT,
        RequirementType.CONSTRAINT,
        RequirementType.CONSTRAINT,
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "requirement_section_qualification_type_normalization" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_normalizes_bracketed_harness_cardinality_requirement(
    session_factory: sessionmaker[Session],
) -> None:
    original = (
        "不要求 React / Electron / Python / 工程化四个方向都精通,"
        "但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向。"
    )
    evidence = f"4.{original}"
    description = (
        "【任职要求】\n"
        "3.工程能力扎实,至少在以下一个方向非常熟练(会其中一个方向即可):\n"
        f"{evidence}\n"
        "5.熟练使用 AI Agent 工具进行真实软件开发,对 Agent 产品有高强度使用经验。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.RESPONSIBILITY,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=evidence,
            confidence=1.0,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_bracketed_harness_cardinality_requirement",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, original),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "requirement_section_qualification_type_normalization" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


def test_workflow_collapses_same_line_qualification_fragments_and_soft_alternative_group(
    session_factory: sessionmaker[Session],
) -> None:
    prompt_requirement = (
        "熟悉Prompt工程,能独立设计结构化Prompt,具备上下文管理与复杂意图拆解能力"
    )
    rag_requirement = (
        "理解RAG、向量数据库、Function Calling等核心技术,能独立完成原型验证与方案评估"
    )
    scenario_requirement = (
        "具备良好的研发场景理解与快速学习能力,能将业务需求转化为可落地的Agent方案"
    )
    soft_requirement = (
        "有MCP协议实践、研发效能/DevOps工具链经验,"
        "或熟练使用Cursor、Claude Code等AI工具链者优先"
    )
    prompt_evidence = f"3. {prompt_requirement};"
    rag_evidence = f"4. {rag_requirement};"
    scenario_evidence = f"5. {scenario_requirement};"
    soft_evidence = f"6. {soft_requirement}。"
    description = "\n".join(
        (
            "任职要求",
            prompt_evidence,
            rag_evidence,
            scenario_evidence,
            soft_evidence,
        )
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=prompt_requirement,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=prompt_requirement,
            confidence=0.98,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="能独立设计结构化Prompt,具备上下文管理与复杂意图拆解能力",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="能独立设计结构化Prompt,具备上下文管理与复杂意图拆解能力",
            confidence=0.96,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="具备上下文管理",
            normalized_capability="上下文管理",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=prompt_evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="复杂意图拆解能力",
            normalized_capability="复杂意图拆解",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=prompt_evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="理解RAG",
            normalized_capability="RAG",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=rag_evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="向量数据库",
            normalized_capability="向量数据库",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=rag_evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="Function Calling",
            normalized_capability="Function Calling",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=rag_evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="能独立完成原型验证与方案评估",
            normalized_capability="原型验证与方案评估",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=rag_evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="具备良好的研发场景理解",
            normalized_capability="研发场景理解",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=scenario_evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text="快速学习能力,能将业务需求转化为可落地的Agent方案",
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span="快速学习能力,能将业务需求转化为可落地的Agent方案",
            confidence=0.96,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="能将业务需求转化为可落地的Agent方案",
            normalized_capability="业务需求转化为Agent方案",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=scenario_evidence,
            confidence=0.95,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="有MCP协议实践",
            normalized_capability="MCP协议实践",
            importance=RequirementImportance.PREFERRED,
            evidence_span=soft_evidence,
            confidence=0.94,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text="研发效能/DevOps工具链经验",
            normalized_capability="DevOps工具链",
            importance=RequirementImportance.PREFERRED,
            evidence_span=soft_evidence,
            confidence=0.94,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="熟练使用Cursor",
            normalized_capability="Cursor",
            importance=RequirementImportance.PREFERRED,
            evidence_span=soft_evidence,
            confidence=0.94,
        ),
        ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text="Claude Code等AI工具链者优先",
            normalized_capability="Claude Code",
            importance=RequirementImportance.PREFERRED,
            evidence_span=soft_evidence,
            confidence=0.94,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_same_line_qualification_fragment_collapse",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, prompt_requirement),
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, rag_requirement),
        (RequirementType.CONSTRAINT, RequirementImportance.MUST_HAVE, scenario_requirement),
        (RequirementType.CONSTRAINT, RequirementImportance.PREFERRED, soft_requirement),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        strategies = {repair["strategy"] for repair in trace.output["semanticRepairs"]}
        assert "collapse_compound_requirement_line" in strategies
        assert "collapse_preferred_alternative_group" in strategies


def test_workflow_keeps_plain_domain_fact_in_requirement_section_as_domain(
    session_factory: sessionmaker[Session],
) -> None:
    original = "熟悉汽车制造行业"
    description = (
        f"任职要求\n1.{original}\n2.熟练使用Python。\n"
        "3.具备良好的工程实践、测试意识与线上问题排查能力。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.DOMAIN,
            original_text=original,
            normalized_capability="汽车制造",
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_plain_requirement_domain_fact",
        description=description,
    )

    assert proposal.requirements[0].type is RequirementType.DOMAIN


def test_workflow_splits_hard_preferred_hard_mixed_scope_experience(
    session_factory: sessionmaker[Session],
) -> None:
    hard_prefix = "5.有成功主导千万级以上AI项目的经验"
    soft = "熟悉车企数字化转型路径者优先"
    hard_tail = "需要有车端经验,非车端经验的无法到副总师的层级"
    original = f"{hard_prefix},{soft}。 {hard_tail}"
    description = (
        f"{original}\n"
        "4.优秀的跨部门沟通与业务理解能力,能快速定位痛点并设计技术方案。"
    )
    extractor = StaticRequirementExtractor(
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=original,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=original,
            confidence=0.95,
        ),
    )

    proposal = _workflow(session_factory, extractor).execute(
        job_id="job_hard_soft_hard_mixed_scope_experience",
        description=description,
    )

    assert [
        (item.type, item.importance, item.original_text)
        for item in proposal.requirements
    ] == [
        (
            RequirementType.EXPERIENCE,
            RequirementImportance.MUST_HAVE,
            hard_prefix,
        ),
        (
            RequirementType.SKILL,
            RequirementImportance.PREFERRED,
            soft,
        ),
        (
            RequirementType.EXPERIENCE,
            RequirementImportance.MUST_HAVE,
            "需要有车端经验",
        ),
    ]
    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.trace_run_id)
        assert trace is not None
        assert "split_hard_preferred_hard_mixed_scope" in {
            repair["strategy"] for repair in trace.output["semanticRepairs"]
        }


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
