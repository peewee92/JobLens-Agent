"""HTTP integration tests for POST /api/v1/profile-proposals."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_profile_extraction_workflow
from app.application.ports.profile_extractor import AbstractProfileExtractor
from app.application.profile_extraction import (
    ProfileExtractionOutput,
    ProfileExtractorResult,
    ProposedEvidence,
    ProposedSkill,
)
from app.db.base import Base
from app.db.models import TraceSpanORM, UserProfileORM
from app.domain.career_context import EvidenceType, SkillLevel
from app.llm import DisabledProfileExtractor, FixtureProfileExtractor
from app.main import app
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows import ProposeProfileFromResumeWorkflow


@pytest.fixture
def api_environment(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'profile-extraction-api.db'}"
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.dependency_overrides[get_profile_extraction_workflow] = lambda: (
        ProposeProfileFromResumeWorkflow(
            FixtureProfileExtractor(),
            lambda: SqlAlchemyTraceUnitOfWork(factory),
        )
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def resume_text() -> str:
    return (
        "8 年前端开发经验。\n"
        "工作经历：负责 Electron 桌面端与 React、TypeScript 业务开发。\n"
        "项目：参与 Agent 功能设计与前后端落地，所有内容均来自真实简历。"
    )


def count_rows(factory: sessionmaker[Session], model: type) -> int:
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_post_profile_proposal_returns_reviewable_output_without_confirming_profile(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment

    response = client.post(
        "/api/v1/profile-proposals",
        json={"resumeText": resume_text()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["runId"].startswith("run_")
    assert body["extractorVersion"] == "profile-extractor-v2"
    assert body["promptVersion"] == "profile-proposal-v1"
    assert body["yearsOfExperience"] == 8
    assert {item["name"] for item in body["skills"]} >= {
        "React",
        "TypeScript",
        "Electron",
        "Agent",
    }
    for evidence in body["evidence"]:
        assert evidence["evidenceSpan"] in resume_text()
    assert count_rows(factory, TraceSpanORM) == 1
    assert count_rows(factory, UserProfileORM) == 0


def test_short_resume_returns_422_without_trace(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment

    response = client.post(
        "/api/v1/profile-proposals",
        json={"resumeText": "too short"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_resume_text"
    assert count_rows(factory, TraceSpanORM) == 0


def test_too_long_resume_returns_stable_422_without_trace(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment

    response = client.post(
        "/api/v1/profile-proposals",
        json={"resumeText": "x" * 30001},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_resume_text"
    assert count_rows(factory, TraceSpanORM) == 0


def test_disabled_provider_returns_503_and_error_trace(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    app.dependency_overrides[get_profile_extraction_workflow] = lambda: (
        ProposeProfileFromResumeWorkflow(
            DisabledProfileExtractor(),
            lambda: SqlAlchemyTraceUnitOfWork(factory),
        )
    )

    response = client.post(
        "/api/v1/profile-proposals",
        json={"resumeText": resume_text()},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "profile_extractor_unavailable"
    with factory() as session:
        trace = session.scalar(select(TraceSpanORM))
        assert trace is not None
        assert trace.error is not None
        assert trace.output is None


class UnsupportedFactExtractor(AbstractProfileExtractor):
    @property
    def model_name(self) -> str:
        return "unsupported-fact"

    def extract(self, text: str) -> ProfileExtractorResult:
        return ProfileExtractorResult(
            output=ProfileExtractionOutput(
                headline="Invented profile",
                years_of_experience=20,
                evidence=(
                    ProposedEvidence(
                        key="fake",
                        type=EvidenceType.ACHIEVEMENT,
                        summary="Built a billion-user system",
                        source="resume",
                        evidence_span="Built a billion-user system",
                    ),
                ),
                skills=(
                    ProposedSkill(
                        name="Distributed Systems",
                        level=SkillLevel.STRONG,
                        evidence_keys=("fake",),
                    ),
                ),
                warnings=(),
            ),
            model=self.model_name,
        )


def test_invalid_provider_output_returns_502_and_never_confirms_profile(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    app.dependency_overrides[get_profile_extraction_workflow] = lambda: (
        ProposeProfileFromResumeWorkflow(
            UnsupportedFactExtractor(),
            lambda: SqlAlchemyTraceUnitOfWork(factory),
        )
    )

    response = client.post(
        "/api/v1/profile-proposals",
        json={"resumeText": resume_text()},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_profile_extractor_output"
    assert count_rows(factory, TraceSpanORM) == 1
    assert count_rows(factory, UserProfileORM) == 0


def test_openapi_contains_profile_proposal_operation(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/profile-proposals"]["post"]
    assert operation["responses"]["200"]
    assert operation["responses"]["502"]
    assert operation["responses"]["503"]
