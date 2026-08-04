"""HTTP integration tests for Job Requirement Extraction."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    get_extract_job_requirements_use_case,
    get_job_requirement_extraction_use_case,
    get_latest_job_requirements_use_case,
)
from app.application.job_requirements import (
    JobRequirementExtractionOutput,
    JobRequirementExtractorResult,
    ProposedJobRequirement,
)
from app.application.job_requirements.use_cases import (
    ExtractJobRequirementsUseCase,
    GetJobRequirementExtractionUseCase,
    GetLatestJobRequirementsUseCase,
)
from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
from app.db.base import Base
from app.db.models import (
    JobORM,
    JobRequirementExtractionORM,
    JobRequirementORM,
    JobSourceORM,
    TraceSpanORM,
)
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.domain.jobs import RemoteConfidence, RemoteStatus
from app.llm import (
    DisabledJobRequirementExtractor,
    FixtureJobRequirementExtractor,
)
from app.main import app
from app.repositories import (
    SqlAlchemyJobQueryRepository,
    SqlAlchemyJobRequirementQueryRepository,
    SqlAlchemyJobRequirementUnitOfWork,
    SqlAlchemyTraceUnitOfWork,
)
from app.workflows import ExtractJobRequirementsWorkflow


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


@pytest.fixture
def api_environment(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'requirements-api.db'}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    jobs = SqlAlchemyJobQueryRepository(factory)
    query = SqlAlchemyJobRequirementQueryRepository(factory)

    def configure(extractor: AbstractJobRequirementExtractor, provider: str) -> None:
        workflow = ExtractJobRequirementsWorkflow(
            extractor,
            lambda: SqlAlchemyTraceUnitOfWork(factory),
        )
        app.dependency_overrides[get_extract_job_requirements_use_case] = lambda: (
            ExtractJobRequirementsUseCase(
                jobs=jobs,
                workflow=workflow,
                uow_factory=lambda: SqlAlchemyJobRequirementUnitOfWork(factory),
                query_repository=query,
                provider=provider,
            )
        )

    configure(FixtureJobRequirementExtractor(), "fixture")
    app.dependency_overrides[get_latest_job_requirements_use_case] = lambda: (
        GetLatestJobRequirementsUseCase(jobs=jobs, repository=query)
    )
    app.dependency_overrides[get_job_requirement_extraction_use_case] = lambda: (
        GetJobRequirementExtractionUseCase(jobs=jobs, repository=query)
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            client.configure_requirement_extractor = configure  # type: ignore[attr-defined]
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed_job(
    factory: sessionmaker[Session],
    *,
    suffix: str,
    description: str | None,
    source_version: str = "test",
    source_raw: dict | None = None,
) -> str:
    job = JobORM(
        id=f"job_{suffix}",
        canonical_key=f"v1:test:id:{suffix}",
        title="AI Application Engineer",
        company="Example Co",
        description=description,
        skills=[],
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
    )
    job.sources.append(
        JobSourceORM(
            id=f"src_{suffix}",
            source="fixture",
            source_job_id=suffix,
            source_url=f"https://example.test/jobs/{suffix}",
            normalized_source_url=f"https://example.test/jobs/{suffix}",
            source_version=source_version,
            source_raw=source_raw or {},
        )
    )
    with factory() as session:
        session.add(job)
        session.commit()
    return job.id


def test_post_get_latest_and_historical_extractions(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    job_id = _seed_job(
        factory,
        suffix="happy",
        description=(
            "岗位要求：\n"
            "熟练掌握 Python 和 FastAPI。\n"
            "具备 3 年以上后端开发经验。\n"
            "有 Docker 使用经验者优先。"
        ),
    )

    first_response = client.post(f"/api/v1/jobs/{job_id}/requirement-extractions")
    second_response = client.post(f"/api/v1/jobs/{job_id}/requirement-extractions")

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    first = first_response.json()
    second = second_response.json()
    assert first["extractionId"] != second["extractionId"]
    assert first["inputHash"] == second["inputHash"]
    assert first["requirementCount"] == len(first["requirements"])
    assert all(
        item["evidenceSpan"] in (
            "岗位要求：\n"
            "熟练掌握 Python 和 FastAPI。\n"
            "具备 3 年以上后端开发经验。\n"
            "有 Docker 使用经验者优先。"
        )
        for item in first["requirements"]
    )

    latest = client.get(f"/api/v1/jobs/{job_id}/requirements")
    historical = client.get(
        f"/api/v1/jobs/{job_id}/requirement-extractions/{first['extractionId']}"
    )
    assert latest.status_code == 200
    assert latest.json()["extractionId"] == second["extractionId"]
    assert historical.status_code == 200
    assert historical.json()["extractionId"] == first["extractionId"]
    assert "description" not in latest.text

    with factory() as session:
        assert int(
            session.scalar(
                select(func.count()).select_from(JobRequirementExtractionORM)
            )
            or 0
        ) == 2
        assert int(
            session.scalar(select(func.count()).select_from(JobRequirementORM)) or 0
        ) > 2
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 2


def test_unknown_job_and_missing_extraction_return_distinct_404s(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    job_id = _seed_job(
        factory,
        suffix="empty",
        description="岗位要求熟练掌握 Python 和 FastAPI，并具备三年以上后端开发经验。",
    )

    unknown = client.post("/api/v1/jobs/job_missing/requirement-extractions")
    empty = client.get(f"/api/v1/jobs/{job_id}/requirements")

    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "job_not_found"
    assert empty.status_code == 404
    assert empty.json()["error"]["code"] == "job_requirement_extraction_not_found"


def test_missing_description_returns_422_without_trace_or_run(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    job_id = _seed_job(factory, suffix="nodesc", description=None)

    response = client.post(f"/api/v1/jobs/{job_id}/requirement-extractions")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "job_description_not_extractable"
    with factory() as session:
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 0
        assert int(
            session.scalar(
                select(func.count()).select_from(JobRequirementExtractionORM)
            )
            or 0
        ) == 0


def test_collector_v140_ineligible_description_is_blocked_before_model_call(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    job_id = _seed_job(
        factory,
        suffix="cardonly",
        description="AI Agent 工程师 15-25K 3-5年 本科 武汉",
        source_version="1.4.0",
        source_raw={
            "descriptionQuality": "card_only",
            "requirementReviewEligible": False,
            "requirementReviewIneligibilityReasons": [
                "detail_not_attempted",
                "missing_full_jd",
            ],
        },
    )

    response = client.post(f"/api/v1/jobs/{job_id}/requirement-extractions")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "job_description_not_extractable"
    assert "card_only" in response.json()["error"]["message"]
    with factory() as session:
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 0
        assert int(
            session.scalar(
                select(func.count()).select_from(JobRequirementExtractionORM)
            )
            or 0
        ) == 0


def test_collector_v141_full_jd_can_run_requirement_extraction(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    job_id = _seed_job(
        factory,
        suffix="fulljd",
        description=(
            "岗位职责：负责 AI Agent 应用设计、开发和线上问题排查。\n"
            "任职要求：熟练掌握 Python 和 FastAPI，具备三年以上后端开发经验。\n"
            "有 Docker、RAG 和工具调用工作流经验者优先。"
        ),
        source_version="1.4.1",
        source_raw={
            "descriptionQuality": "full_jd",
            "requirementReviewEligible": True,
            "requirementReviewIneligibilityReasons": [],
        },
    )

    response = client.post(f"/api/v1/jobs/{job_id}/requirement-extractions")

    assert response.status_code == 201
    assert response.json()["requirementCount"] > 0


def test_disabled_and_invalid_provider_results_map_to_stable_errors(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    job_id = _seed_job(
        factory,
        suffix="provider",
        description=(
            "岗位要求熟练掌握 Python 和 FastAPI，并具备三年以上后端开发经验，"
            "同时需要负责接口设计和线上问题排查。"
        ),
    )

    client.configure_requirement_extractor(  # type: ignore[attr-defined]
        DisabledJobRequirementExtractor(),
        "disabled",
    )
    disabled = client.post(f"/api/v1/jobs/{job_id}/requirement-extractions")
    client.configure_requirement_extractor(  # type: ignore[attr-defined]
        HallucinatingExtractor(),
        "simulated-live",
    )
    invalid = client.post(f"/api/v1/jobs/{job_id}/requirement-extractions")

    assert disabled.status_code == 503
    assert disabled.json()["error"]["code"] == "requirement_extractor_unavailable"
    assert invalid.status_code == 502
    assert invalid.json()["error"]["code"] == "invalid_requirement_extractor_output"
    with factory() as session:
        assert int(session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0) == 2
        assert int(
            session.scalar(
                select(func.count()).select_from(JobRequirementExtractionORM)
            )
            or 0
        ) == 0


def test_openapi_registers_requirement_routes_and_errors(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    post = paths["/api/v1/jobs/{job_id}/requirement-extractions"]["post"]
    assert {"201", "404", "422", "502", "503"} <= set(post["responses"])
    assert paths["/api/v1/jobs/{job_id}/requirements"]["get"]
    assert paths[
        "/api/v1/jobs/{job_id}/requirement-extractions/{extraction_id}"
    ]["get"]
