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
    assert proposal.extractor_version == "requirement-extractor-v4"
    assert proposal.prompt_version == "requirement-extraction-v1"
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
