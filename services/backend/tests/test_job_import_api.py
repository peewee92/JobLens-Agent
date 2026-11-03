"""HTTP integration tests for POST /api/v1/job-imports."""
from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_import_jobs_use_case
from app.application.job_imports import ImportJobsUseCase
from app.application.job_imports.adapter import adapt_collector_report
from app.application.job_imports.normalizer import normalize_adapted_report
from app.db.base import Base
from app.db.models import JobImportItemORM, JobImportORM, JobORM, JobSourceORM
from app.domain.jobs import ImportOutcome
from app.main import app
from app.repositories import SqlAlchemyUnitOfWork

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
    database_url = f"sqlite+pysqlite:///{tmp_path / 'job-import-api.db'}"
    engine = create_engine(database_url)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    use_case = ImportJobsUseCase(lambda: SqlAlchemyUnitOfWork(factory))
    app.dependency_overrides[get_import_jobs_use_case] = lambda: use_case

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def load_report() -> dict[str, Any]:
    return json.loads(SAMPLE_REPORT.read_text(encoding="utf-8"))


def count_rows(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_pasted_jobs_without_links_preserve_text_and_reuse_exact_content(api_environment):
    from app.repositories.sqlalchemy_job_query_repository import SqlAlchemyJobQueryRepository
    client, factory = api_environment
    payload = {"title": "AI 应用工程师", "company": "示例公司", "description": "岗位要求：\n熟悉 Python 和 FastAPI。\n能够解释项目经历。"}
    first = client.post("/api/v1/job-imports/manual", json=payload)
    assert first.status_code == 201
    assert first.json()["jobId"].startswith("job_")
    assert first.json()["created"] == 1
    replay = client.post("/api/v1/job-imports/manual", json=payload)
    assert replay.status_code == 201 and replay.json()["updated"] == 1
    assert replay.json()["jobId"] == first.json()["jobId"]
    other = client.post("/api/v1/job-imports/manual", json={**payload, "description": "另一份岗位描述"})
    assert other.status_code == 201 and other.json()["created"] == 1
    with factory() as session:
        assert count_rows(session, JobORM) == 2
        assert count_rows(session, JobSourceORM) == 2
        original = session.scalar(select(JobORM).where(JobORM.description == payload["description"]))
        source = session.scalar(select(JobSourceORM).where(JobSourceORM.job_id == original.id))
        assert source.source == "manual" and source.source_url == "" and source.normalized_source_url is None
        assert source.source_raw["description"] == payload["description"]
        assert source.source_raw["provenanceKind"] == "user_paste"
        assert source.source_raw["sourceUrl"] is None
        assert original.remote_status.value == "unknown"
        assert original.education is None and original.skills == []
        batch = session.get(JobImportORM, first.json()["importId"])
        assert batch.collector_version is None and batch.source_version == "manual-paste-v1"
        item = session.scalar(select(JobImportItemORM).where(JobImportItemORM.import_id == batch.id))
        assert item.source_raw_snapshot["description"] == payload["description"]
        job_id = original.id
    detail = SqlAlchemyJobQueryRepository(factory).get_job(job_id)
    assert detail.description == payload["description"] and detail.source_url == ""


def test_pasted_url_is_not_fetched_and_reimport_keeps_job_identity(api_environment):
    client, factory = api_environment
    payload = {"title": "开发工程师", "company": "示例", "description": "旧岗位原文", "sourceUrl": "https://example.org/jobs/123?tracking=1"}
    assert client.post("/api/v1/job-imports/manual", json=payload).json()["created"] == 1
    payload.update(description="新岗位原文", sourceUrl="https://example.org/jobs/123?tracking=2")
    result = client.post("/api/v1/job-imports/manual", json=payload)
    assert result.status_code == 201 and result.json()["updated"] == 1
    with factory() as session:
        assert count_rows(session, JobORM) == 1
        assert session.scalar(select(JobORM.description)) == "新岗位原文"
        assert count_rows(session, JobImportItemORM) == 2


@pytest.mark.parametrize("updates", [
    {"title": "  "}, {"company": ""}, {"description": "\n "}, {"description": "x" * 50001},
    {"sourceUrl": "javascript:alert(1)"}, {"sourceUrl": "https://user:secret@example.org/a"},
    {"remoteStatus": "confirmed"},
])
def test_paste_validation_does_not_write(api_environment, updates):
    client, factory = api_environment
    response = client.post("/api/v1/job-imports/manual", json={
        "title": "岗位", "company": "公司", "description": "真实描述", **updates,
    })
    assert response.status_code == 422
    with factory() as session:
        assert count_rows(session, JobImportORM) == 0


def test_manual_contracts_match_python_models():
    from app.application.job_imports.manual import ManualJobInput
    from app.api.v1.schemas.job_imports import ManualJobImportResponse
    schemas = Path(__file__).resolve().parents[3] / "packages/contracts/schemas"
    for name, model in (("manual-job-input", ManualJobInput), ("manual-job-import-response", ManualJobImportResponse)):
        schema = json.loads((schemas / f"{name}.schema.json").read_text())
        schema.pop("$schema")
        assert schema == model.model_json_schema(by_alias=True)


def test_paste_preserves_original_whitespace(api_environment):
    client, factory = api_environment
    original = "\n  任职要求：Python\r\n有真实项目经历。\n"
    response = client.post("/api/v1/job-imports/manual", json={"title": "岗位", "company": "公司", "description": original})
    assert response.status_code == 201
    with factory() as session:
        assert session.scalar(select(JobORM.description)) == original
        assert session.scalar(select(JobImportItemORM.source_raw_snapshot))["description"] == original


def test_post_job_imports_returns_201_and_persists_complete_batch(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment

    response = client.post("/api/v1/job-imports", json=load_report())

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "importId": body["importId"],
        "sourceVersion": "1.3.1",
        "received": 1,
        "created": 1,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }
    assert body["importId"].startswith("imp_")

    with factory() as session:
        assert count_rows(session, JobORM) == 1
        assert count_rows(session, JobSourceORM) == 1
        assert count_rows(session, JobImportORM) == 1
        assert count_rows(session, JobImportItemORM) == 1
        item = session.scalar(select(JobImportItemORM))
        assert item is not None
        assert item.outcome is ImportOutcome.CREATED


@pytest.mark.parametrize("collector_version", ["1.4.1", "1.4.2", "1.4.3", "1.4.4", "1.4.5", "1.4.6", "1.4.7", "1.4.8", "1.4.9"])
def test_collector_v14x_quality_evidence_is_accepted_and_preserved(
    api_environment: tuple[TestClient, sessionmaker[Session]],
    collector_version: str,
) -> None:
    client, factory = api_environment
    payload = load_report()
    payload["version"] = collector_version
    payload["jobs"][0].update(
        {
            "detailAttempted": True,
            "detailSucceeded": True,
            "descriptionSource": "selector:.job-sec-text",
            "descriptionSelectorTrust": "trusted",
            "descriptionSanitized": False,
            "descriptionQuality": "full_jd",
            "descriptionLength": len(payload["jobs"][0]["description"]),
            "descriptionHash": "fnv1a32:12345678",
            "descriptionNoiseCount": 0,
            "requirementReviewEligible": True,
            "requirementReviewIneligibilityReasons": [],
        }
    )
    if collector_version == "1.4.9":
        payload["jobs"][0].update(
            {
                "recruiterActive": "本月活跃",
                "recruiterActivityStatus": "known",
                "recruiterActivityMaxAgeDays": 30,
                "recruiterActivityMinAgeDays": 0,
            }
        )

    response = client.post("/api/v1/job-imports", json=payload)

    assert response.status_code == 201
    assert response.json()["sourceVersion"] == collector_version
    with factory() as session:
        source = session.scalar(select(JobSourceORM))
        assert source is not None
        assert source.source_version == collector_version
        assert source.source_raw["descriptionQuality"] == "full_jd"
        assert source.source_raw["descriptionSelectorTrust"] == "trusted"
        assert source.source_raw["descriptionNoiseCount"] == 0
        assert source.source_raw["requirementReviewEligible"] is True
        if collector_version == "1.4.9":
            assert source.source_raw["recruiterActive"] == "本月活跃"
            assert source.source_raw["recruiterActivityStatus"] == "known"
            assert source.source_raw["recruiterActivityMaxAgeDays"] == 30


def test_reimport_returns_updated_without_duplicate_job(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment

    first = client.post("/api/v1/job-imports", json=load_report())
    second_payload = load_report()
    second_payload["generatedAt"] = "2026-07-22T00:00:00.000Z"
    second_payload["jobs"][0]["title"] = "高级 AI 应用开发工程师"
    second = client.post("/api/v1/job-imports", json=second_payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["created"] == 1
    assert second.json()["created"] == 0
    assert second.json()["updated"] == 1
    assert first.json()["importId"] != second.json()["importId"]

    with factory() as session:
        assert count_rows(session, JobORM) == 1
        assert count_rows(session, JobSourceORM) == 1
        assert count_rows(session, JobImportORM) == 2
        assert count_rows(session, JobImportItemORM) == 2


def test_item_error_returns_completed_batch_with_errors(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    payload = load_report()
    invalid_job = deepcopy(payload["jobs"][0])
    invalid_job.pop("company")
    payload["jobs"].append(invalid_job)

    response = client.post("/api/v1/job-imports", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["received"] == 2
    assert body["created"] == 1
    assert body["updated"] == 0
    assert body["skipped"] == 1
    assert body["errors"] == [
        {
            "index": 1,
            "stage": "adapter",
            "code": "invalid_job_payload",
            "message": body["errors"][0]["message"],
        }
    ]

    with factory() as session:
        items = list(
            session.scalars(
                select(JobImportItemORM).order_by(JobImportItemORM.input_index)
            )
        )
        assert [item.outcome for item in items] == [
            ImportOutcome.CREATED,
            ImportOutcome.ERROR,
        ]


def test_unsupported_version_returns_422_without_database_changes(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    payload = load_report()
    payload["version"] = "9.9.9"

    response = client.post("/api/v1/job-imports", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "unsupported_collector_version",
            "message": "unsupported Collector version: 9.9.9",
        }
    }
    with factory() as session:
        assert count_rows(session, JobImportORM) == 0
        assert count_rows(session, JobImportItemORM) == 0


def test_invalid_report_returns_structured_422(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    payload = load_report()
    payload.pop("version")

    response = client.post("/api/v1/job-imports", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_collector_report"
    with factory() as session:
        assert count_rows(session, JobImportORM) == 0


def test_non_object_request_body_returns_request_validation_error(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment

    response = client.post("/api/v1/job-imports", json=["not", "an", "object"])

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "request_validation_error",
            "message": "Request body or parameters are invalid.",
        }
    }
    with factory() as session:
        assert count_rows(session, JobImportORM) == 0


def test_identity_conflict_returns_409_and_rolls_back_new_batch(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    payload = load_report()
    normalized = normalize_adapted_report(adapt_collector_report(payload)).jobs[0]
    conflicting = replace(
        normalized,
        canonical_key="v1:boss:id:legacy-job",
        title="Legacy Job",
    )

    with SqlAlchemyUnitOfWork(factory) as uow:
        existing_job_id = uow.jobs.add_job(conflicting)
        uow.jobs.add_source(existing_job_id, conflicting)
        uow.commit()

    response = client.post("/api/v1/job-imports", json=payload)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "import_identity_conflict"
    with factory() as session:
        assert count_rows(session, JobORM) == 1
        assert count_rows(session, JobSourceORM) == 1
        assert count_rows(session, JobImportORM) == 0
        assert count_rows(session, JobImportItemORM) == 0


def test_unexpected_error_returns_generic_500_without_internal_details(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    class FailingUseCase:
        def execute(self, _payload: dict[str, Any]) -> None:
            raise RuntimeError("sqlite:////secret/local/path.db")

    app.dependency_overrides[get_import_jobs_use_case] = lambda: FailingUseCase()
    response = client.post("/api/v1/job-imports", json=load_report())

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "An unexpected server error occurred.",
        }
    }
    assert "secret" not in response.text
    assert "sqlite" not in response.text


def test_openapi_registers_job_import_endpoint(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/job-imports"]["post"]
    assert "job-imports" in operation["tags"]
    assert set(operation["responses"]) >= {"201", "409", "422", "500"}
