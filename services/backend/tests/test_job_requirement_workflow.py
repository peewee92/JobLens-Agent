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
    assert proposal.extractor_version == "requirement-extractor-v6"
    assert proposal.prompt_version == "requirement-extraction-v2"
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

    assert proposal.extractor_version == "requirement-extractor-v6"
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
