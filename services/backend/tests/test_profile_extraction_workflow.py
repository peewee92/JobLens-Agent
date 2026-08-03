"""Workflow and Trace tests for Profile Extraction proposals."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.ports.profile_extractor import AbstractProfileExtractor
from app.application.profile_extraction import (
    InvalidProfileExtractorOutputError,
    InvalidResumeTextError,
    ProfileExtractionOutput,
    ProfileExtractorFailedError,
    ProfileExtractorResult,
    ProposedEvidence,
    ProposedSkill,
)
from app.db.base import Base
from app.db.models import TraceSpanORM, UserProfileORM
from app.domain.career_context import EvidenceType, SkillLevel
from app.llm import FixtureProfileExtractor
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows import ProposeProfileFromResumeWorkflow


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'profile-trace.db'}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def workflow(
    extractor: AbstractProfileExtractor,
    session_factory: sessionmaker[Session],
) -> ProposeProfileFromResumeWorkflow:
    return ProposeProfileFromResumeWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(session_factory),
    )


def resume_text() -> str:
    return (
        "8 年前端开发经验。\n"
        "工作经历：负责 Electron 桌面端与 React、TypeScript 业务开发，交付企业办公产品。\n"
        "项目：参与 Agent 功能设计与前后端落地。"
    )


def count_rows(session_factory: sessionmaker[Session], model: type) -> int:
    with session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_success_returns_proposal_and_writes_sanitized_trace(
    session_factory: sessionmaker[Session],
) -> None:
    proposal = workflow(FixtureProfileExtractor(), session_factory).execute(resume_text())

    assert proposal.run_id.startswith("run_")
    assert proposal.headline == "8 年前端开发经验。"
    assert proposal.years_of_experience == 8
    assert {skill.name for skill in proposal.skills} >= {
        "React",
        "TypeScript",
        "Electron",
        "Agent",
    }
    assert count_rows(session_factory, UserProfileORM) == 0

    with session_factory() as session:
        trace = session.get(TraceSpanORM, proposal.run_id)
        assert trace is not None
        assert trace.capability == "profile_extraction"
        assert trace.version == "profile-extractor-v1"
        assert trace.prompt_version == "profile-proposal-v1"
        assert trace.model == "fixture-profile-extractor"
        assert trace.error is None
        assert trace.output["headline"] == proposal.headline
        assert trace.input_refs["characterCount"] == len(resume_text())
        assert len(trace.input_refs["resumeSha256"]) == 64
        assert "resumeText" not in trace.input_refs
        assert resume_text() not in str(trace.input_refs)


def test_invalid_resume_text_opens_no_provider_or_trace(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(InvalidResumeTextError):
        workflow(FixtureProfileExtractor(), session_factory).execute("too short")

    assert count_rows(session_factory, TraceSpanORM) == 0


class InvalidSpanExtractor(AbstractProfileExtractor):
    @property
    def model_name(self) -> str:
        return "invalid-span"

    def extract(self, resume_text: str) -> ProfileExtractorResult:
        return ProfileExtractorResult(
            output=ProfileExtractionOutput(
                headline="Frontend Engineer",
                years_of_experience=8,
                evidence=(
                    ProposedEvidence(
                        key="invented",
                        type=EvidenceType.PROJECT,
                        summary="Invented evidence",
                        source="resume",
                        evidence_span="This text is not in the resume",
                    ),
                ),
                skills=(
                    ProposedSkill(
                        name="React",
                        level=SkillLevel.STRONG,
                        evidence_keys=("invented",),
                    ),
                ),
                warnings=(),
            ),
            model=self.model_name,
        )


def test_invalid_provider_output_is_rejected_and_traced(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(
        InvalidProfileExtractorOutputError,
        match="does not occur",
    ):
        workflow(InvalidSpanExtractor(), session_factory).execute(resume_text())

    with session_factory() as session:
        trace = session.scalar(select(TraceSpanORM))
        assert trace is not None
        assert "does not occur" in trace.error
        assert trace.output["evidence"][0]["key"] == "invented"
    assert count_rows(session_factory, UserProfileORM) == 0


class FailingExtractor(AbstractProfileExtractor):
    @property
    def model_name(self) -> str:
        return "failing-provider"

    def extract(self, resume_text: str) -> ProfileExtractorResult:
        raise ProfileExtractorFailedError("simulated provider outage")


class LeakyUnexpectedExtractor(AbstractProfileExtractor):
    @property
    def model_name(self) -> str:
        return "leaky-unexpected"

    def extract(self, resume_text: str) -> ProfileExtractorResult:
        raise RuntimeError(f"unexpected failure with input: {resume_text}")


def test_unexpected_provider_error_trace_does_not_copy_resume_text(
    session_factory: sessionmaker[Session],
) -> None:
    text = resume_text()

    with pytest.raises(ProfileExtractorFailedError):
        workflow(LeakyUnexpectedExtractor(), session_factory).execute(text)

    with session_factory() as session:
        trace = session.scalar(select(TraceSpanORM))
        assert trace is not None
        assert trace.error == "RuntimeError: unexpected extractor error"
        assert text not in trace.error


def test_provider_failure_writes_error_trace(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(ProfileExtractorFailedError, match="simulated provider outage"):
        workflow(FailingExtractor(), session_factory).execute(resume_text())

    with session_factory() as session:
        trace = session.scalar(select(TraceSpanORM))
        assert trace is not None
        assert trace.model == "failing-provider"
        assert trace.output is None
        assert trace.error == "simulated provider outage"
