"""HTTP integration tests for GET /api/v1/job-imports/{import_id}."""
from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    get_import_jobs_use_case,
    get_job_import_detail_use_case,
)
from app.application.job_import_queries.use_cases import GetJobImportDetailUseCase
from app.application.job_imports import ImportJobsUseCase
from app.db.base import Base
from app.main import app
from app.repositories import (
    SqlAlchemyJobImportQueryRepository,
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
) -> Iterator[TestClient]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'job-import-detail-api.db'}"
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    import_use_case = ImportJobsUseCase(
        lambda: SqlAlchemyUnitOfWork(factory)
    )
    detail_use_case = GetJobImportDetailUseCase(
        SqlAlchemyJobImportQueryRepository(factory)
    )
    app.dependency_overrides[get_import_jobs_use_case] = lambda: import_use_case
    app.dependency_overrides[get_job_import_detail_use_case] = lambda: detail_use_case

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def load_report() -> dict:
    return json.loads(SAMPLE_REPORT.read_text(encoding="utf-8"))


def test_get_import_detail_returns_auditable_sanitized_response(
    api_environment: TestClient,
) -> None:
    payload = load_report()
    invalid = deepcopy(payload["jobs"][0])
    invalid.pop("company")
    payload["jobs"].append(invalid)

    created = api_environment.post("/api/v1/job-imports", json=payload)
    assert created.status_code == 201
    import_id = created.json()["importId"]

    response = api_environment.get(f"/api/v1/job-imports/{import_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["importId"] == import_id
    assert body["sourceVersion"] == "1.3.1"
    assert body["collectorVersion"] == "1.3.1"
    assert body["received"] == 2
    assert body["created"] == 1
    assert body["updated"] == 0
    assert body["skipped"] == 1
    assert body["received"] == body["created"] + body["updated"] + body["skipped"]
    assert body["searchIntentSnapshot"]["selectedCities"][0]["name"] == "武汉"
    assert body["sourceSnapshot"]["candidateCount"] == 0
    assert [item["inputIndex"] for item in body["items"]] == [0, 1]
    assert [item["outcome"] for item in body["items"]] == ["created", "error"]
    assert body["items"][0]["jobId"].startswith("job_")
    assert body["items"][0]["jobSourceId"].startswith("src_")
    assert body["items"][1]["errorCode"] == "invalid_job_payload"
    assert body["errors"][0]["index"] == 1
    assert "raw" not in body["errors"][0]
    serialized = json.dumps(body, ensure_ascii=False)
    assert "collectorOnlyField" not in serialized
    assert "sourceRaw" not in serialized
    assert "canonicalKey" not in serialized


def test_get_import_detail_returns_structured_404(
    api_environment: TestClient,
) -> None:
    response = api_environment.get("/api/v1/job-imports/imp_missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "job_import_not_found",
            "message": "Job import not found: imp_missing",
        }
    }


def test_openapi_contains_job_import_detail_operation(
    api_environment: TestClient,
) -> None:
    openapi = api_environment.get("/openapi.json")

    assert openapi.status_code == 200
    operation = openapi.json()["paths"]["/api/v1/job-imports/{import_id}"]["get"]
    assert operation["responses"]["200"]
    assert operation["responses"]["404"]
