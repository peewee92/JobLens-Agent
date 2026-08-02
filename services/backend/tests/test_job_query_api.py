"""HTTP integration tests for Job Pool list and detail endpoints."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_import_jobs_use_case, get_job_query_repository
from app.application.job_imports import ImportJobsUseCase
from app.db.base import Base
from app.db.models import JobORM, JobSourceORM
from app.domain.jobs import RemoteConfidence, RemoteStatus
from app.main import app
from app.repositories import (
    SqlAlchemyJobQueryRepository,
    SqlAlchemyUnitOfWork,
)

SAMPLE_REPORT = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "samples"
    / "collector-report-minimal.json"
)


@pytest.fixture
def api_environment(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'job-query-api.db'}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    import_use_case = ImportJobsUseCase(lambda: SqlAlchemyUnitOfWork(factory))
    query_repository = SqlAlchemyJobQueryRepository(factory)
    app.dependency_overrides[get_import_jobs_use_case] = lambda: import_use_case
    app.dependency_overrides[get_job_query_repository] = lambda: query_repository

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def load_report() -> dict:
    return json.loads(SAMPLE_REPORT.read_text(encoding="utf-8"))


def dt(day: int) -> datetime:
    return datetime(2026, 8, day, 8, 0, tzinfo=UTC)


def add_job(
    factory: sessionmaker[Session],
    *,
    job_id: str,
    title: str,
    company: str,
    area: str,
    salary_min: float | None,
    salary_max: float | None,
    remote_status: RemoteStatus,
    source_id: str,
    source: str = "boss",
    last_seen: datetime | None = None,
) -> None:
    seen_at = last_seen or dt(1)
    with factory() as session:
        session.add(
            JobORM(
                id=job_id,
                canonical_key=f"v1:{job_id}",
                title=title,
                company=company,
                area=area,
                salary_min_k=salary_min,
                salary_max_k=salary_max,
                experience="3-5年",
                education="本科",
                description=f"{title} description",
                skills=["Python"],
                remote_status=remote_status,
                remote_confidence=RemoteConfidence.HIGH,
            )
        )
        session.flush()
        session.add(
            JobSourceORM(
                id=source_id,
                job_id=job_id,
                source=source,
                source_job_id=job_id,
                source_url=f"https://{source}.example/{job_id}",
                normalized_source_url=f"https://{source}.example/{job_id}",
                source_version="1.3.1",
                source_raw={"private": "must not leak"},
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                collected_at=seen_at,
            )
        )
        session.commit()


def test_imported_job_is_immediately_visible_in_job_pool(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    imported = client.post("/api/v1/job-imports", json=load_report())
    listed = client.get("/api/v1/jobs")

    assert imported.status_code == 201
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["items"][0]["title"] == "AI 应用开发工程师"
    assert body["items"][0]["source"] == "boss"
    assert "canonicalKey" not in body["items"][0]
    assert "sourceRaw" not in body["items"][0]
    assert "normalizedSourceUrl" not in body["items"][0]


def test_list_filters_and_salary_semantics(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    add_job(
        factory,
        job_id="job_a",
        title="AI Backend Engineer",
        company="Alpha",
        area="武汉·光谷",
        salary_min=15,
        salary_max=30,
        remote_status=RemoteStatus.CONFIRMED,
        source_id="src_a",
    )
    add_job(
        factory,
        job_id="job_b",
        title="React Engineer",
        company="Beta",
        area="武汉",
        salary_min=10,
        salary_max=18,
        remote_status=RemoteStatus.UNKNOWN,
        source_id="src_b",
    )
    add_job(
        factory,
        job_id="job_c",
        title="AI Backend Engineer",
        company="Gamma",
        area="上海",
        salary_min=25,
        salary_max=40,
        remote_status=RemoteStatus.CONFIRMED,
        source_id="src_c",
    )

    response = client.get(
        "/api/v1/jobs",
        params={
            "q": "backend",
            "city": "武汉",
            "minSalaryK": 20,
            "remoteStatus": "confirmed",
            "source": "boss",
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [item["id"] for item in response.json()["items"]] == ["job_a"]


def test_list_paginates_stably_and_deduplicates_multiple_sources(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    for index in range(3):
        add_job(
            factory,
            job_id=f"job_{index}",
            title=f"Job {index}",
            company="Example",
            area="武汉",
            salary_min=10 + index,
            salary_max=20 + index,
            remote_status=RemoteStatus.UNKNOWN,
            source_id=f"src_{index}",
            last_seen=dt(1),
        )

    with factory() as session:
        session.add(
            JobSourceORM(
                id="src_0_new",
                job_id="job_0",
                source="career-site",
                source_job_id="job_0-career",
                source_url="https://career.example/job_0",
                normalized_source_url="https://career.example/job_0",
                source_version="web-v1",
                source_raw={},
                first_seen_at=dt(2),
                last_seen_at=dt(3),
                collected_at=dt(3),
            )
        )
        session.commit()

    first = client.get("/api/v1/jobs", params={"limit": 2, "offset": 0})
    second = client.get("/api/v1/jobs", params={"limit": 2, "offset": 2})

    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 3
    first_ids = [item["id"] for item in first.json()["items"]]
    second_ids = [item["id"] for item in second.json()["items"]]
    assert first_ids == ["job_0", "job_1"]
    assert second_ids == ["job_2"]
    assert set(first_ids).isdisjoint(second_ids)
    assert first.json()["items"][0]["source"] == "career-site"


def test_get_job_returns_detail_without_internal_or_raw_fields(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    add_job(
        factory,
        job_id="job_detail",
        title="AI Engineer",
        company="Example",
        area="武汉",
        salary_min=20,
        salary_max=35,
        remote_status=RemoteStatus.CONFIRMED,
        source_id="src_detail",
    )

    response = client.get("/api/v1/jobs/job_detail")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "job_detail"
    assert body["description"] == "AI Engineer description"
    assert body["skills"] == ["Python"]
    assert "canonicalKey" not in body
    assert "canonicalKeyVersion" not in body
    assert "sourceRaw" not in body
    assert "normalizedSourceUrl" not in body


def test_get_missing_job_returns_structured_404(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    response = client.get("/api/v1/jobs/job_missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "job_not_found",
            "message": "Job not found: job_missing",
        }
    }


def test_invalid_query_parameters_return_structured_422(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    response = client.get("/api/v1/jobs", params={"limit": 101})

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "request_validation_error",
            "message": "Request body or parameters are invalid.",
        }
    }


def test_openapi_exposes_job_query_routes(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/jobs" in paths
    assert "/api/v1/jobs/{job_id}" in paths
    assert "get" in paths["/api/v1/jobs"]
    assert "get" in paths["/api/v1/jobs/{job_id}"]


def test_job_queries_do_not_change_database_rows(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    add_job(
        factory,
        job_id="job_read_only",
        title="Read Only",
        company="Example",
        area="武汉",
        salary_min=10,
        salary_max=20,
        remote_status=RemoteStatus.UNKNOWN,
        source_id="src_read_only",
    )

    with factory() as session:
        before = (
            session.scalar(select(func.count()).select_from(JobORM)),
            session.scalar(select(func.count()).select_from(JobSourceORM)),
        )

    client.get("/api/v1/jobs")
    client.get("/api/v1/jobs/job_read_only")

    with factory() as session:
        after = (
            session.scalar(select(func.count()).select_from(JobORM)),
            session.scalar(select(func.count()).select_from(JobSourceORM)),
        )
    assert after == before
