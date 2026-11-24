"""HTTP integration tests for POST /api/v1/job-imports."""
from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from typing import Any
from unicodedata import normalize

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_import_jobs_use_case, get_revise_manual_job_description
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
    from app.application.job_queries.manual_description import ReviseManualJobDescription
    from app.repositories.sqlalchemy_manual_job_description import SqlAlchemyManualJobDescription
    app.dependency_overrides[get_import_jobs_use_case] = lambda: use_case
    app.dependency_overrides[get_revise_manual_job_description] = lambda: ReviseManualJobDescription(SqlAlchemyManualJobDescription(factory))

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


@pytest.mark.parametrize("collector_version", ["1.4.1", "1.4.2", "1.4.3", "1.4.4", "1.4.5", "1.4.6", "1.4.7", "1.4.8", "1.4.9", "1.5.0", "1.6.0"])
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
    if collector_version in ("1.4.9", "1.5.0"):
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
        if collector_version in ("1.4.9", "1.5.0"):
            assert source.source_raw["recruiterActive"] == "本月活跃"
            assert source.source_raw["recruiterActivityStatus"] == "known"
            assert source.source_raw["recruiterActivityMaxAgeDays"] == 30


def test_quick_save_single_job_preserves_the_reviewed_description_and_reuses_job(api_environment) -> None:
    client, factory = api_environment
    description = "岗位职责：负责服务接口设计和上线维护。\n任职要求：熟悉 Python 并具备三年以上开发经验。"
    url = "https://www.zhipin.com/job_detail/example.html"
    payload = {
        "version": "1.6.0",
        "generatedAt": "2026-11-23T00:00:00.000Z",
        "config": {},
        "statistics": {},
        "jobs": [{
            "title": "后端工程师", "company": "示例公司", "url": url, "description": description,
            "area": None, "salaryMinK": None, "salaryMaxK": None,
            "detailAttempted": True, "detailSucceeded": True, "descriptionSource": "selector:.job-sec-text",
            "descriptionSelectorTrust": "trusted", "descriptionQuality": "full_jd", "requirementReviewEligible": True,
        }],
        "candidates": [],
    }

    first = client.post("/api/v1/job-imports", json=payload)
    assert first.status_code == 201
    assert first.json() == {
        "importId": first.json()["importId"], "sourceVersion": "1.6.0",
        "received": 1, "created": 1, "updated": 0, "skipped": 0, "errors": [],
    }
    replay = client.post("/api/v1/job-imports", json=payload)
    assert replay.status_code == 201
    assert replay.json()["received"] == 1
    assert replay.json()["created"] == 0
    assert replay.json()["errors"] == []
    assert replay.json()["importId"] != first.json()["importId"]
    with factory() as session:
        assert count_rows(session, JobORM) == count_rows(session, JobSourceORM) == 1
        assert session.scalar(select(JobORM.description)) == normalize("NFKC", description)
        assert session.scalar(select(JobSourceORM)).source_raw["description"] == description
        items = session.scalars(select(JobImportItemORM)).all()
        assert len(items) == 2
        assert items[0].job_id == items[1].job_id
        assert all(item.source_raw_snapshot["url"] == url for item in items)
        assert all(item.source_raw_snapshot["description"] == description for item in items)


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


@pytest.mark.parametrize("source_url", [None, "https://example.org/jobs/to-edit"])
def test_manual_correction_preserves_identity_and_original_observations(api_environment, source_url):
    from app.application.job_queries.manual_description import description_digest
    from app.api.v1.jobs import ManualJobDescriptionRequest, ManualJobDescriptionResponse

    client, factory = api_environment
    original = {"title": "应用工程师", "company": "合成测试", "description": "仅岗位标题", "sourceUrl": source_url}
    start = client.post("/api/v1/job-imports/manual", json=original).json()
    job_id = start["jobId"]
    endpoint = f"/api/v1/jobs/{job_id}/manual-description"
    expected = description_digest(original["description"])
    full = "工作职责：开发和维护内部工具，并跟进服务可用性。\n任职要求：熟练掌握 Python，能够真实讲述实践项目。"
    request = {"description": full, "expectedSha256": expected}
    assert client.put(endpoint, json={**request, "description": "???"}).status_code == 422
    assert client.put(endpoint, json={**request, "expectedSha256": "0" * 64}).status_code == 409

    schemas = Path(__file__).resolve().parents[3] / "packages/contracts/schemas"
    for suffix, model in (("request", ManualJobDescriptionRequest), ("response", ManualJobDescriptionResponse)):
        schema = json.loads((schemas / f"manual-job-description-{suffix}.schema.json").read_text())
        schema.pop("$schema")
        assert schema == model.model_json_schema(by_alias=True)
    changed = client.put(endpoint, json=request)
    assert changed.status_code == 200, changed.text
    assert changed.json() == {"jobId": job_id, "descriptionSha256": description_digest(full), "changed": True}
    replay = client.put(endpoint, json=request)
    assert replay.status_code == 200 and not replay.json()["changed"]
    for paste in (original, {**original, "description": full}, original):
        # A new URL-less paste alias, or the original URL, keeps the same posting.
        output = client.post("/api/v1/job-imports/manual", json=paste).json()
        assert output["jobId"] == job_id and output["created"] == 0
    with factory() as session:
        assert count_rows(session, JobORM) == 1
        assert session.get(JobORM, job_id).description == full
        snapshots = session.scalars(select(JobImportItemORM.source_raw_snapshot)
            .join(JobImportORM).where(JobImportORM.source_version == "manual-description-revision-v1")).all()
        assert len(snapshots) == 1
        assert snapshots[0]["description"] == full and snapshots[0]["previousDescriptionSha256"] == expected
        original_record = session.scalar(select(JobImportItemORM).where(JobImportItemORM.import_id == start["importId"]))
        assert original_record.source_raw_snapshot["description"] == original["description"]


def test_correction_never_modifies_collector_or_merges_another_job(api_environment):
    from app.application.job_queries.manual_description import description_digest

    client, factory = api_environment
    original = "任职要求：熟练掌握 Python，能够说明真实维护经历和服务改进过程，并和团队合作。"
    replacement = original + "\n加分项：熟悉 Docker 部署。"
    data = {"title": "后端工程师", "company": "测试"}
    ids = [client.post("/api/v1/job-imports/manual", json={**data, "description": description}).json()["jobId"]
           for description in (original, replacement)]
    request = {"description": replacement, "expectedSha256": description_digest(original)}
    conflict = client.put(f"/api/v1/jobs/{ids[0]}/manual-description", json=request)
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "manual_description_identity_conflict"
    assert client.post("/api/v1/job-imports", json=load_report()).status_code == 201
    with factory() as session:
        job = session.scalar(select(JobORM).where(JobORM.id.not_in(ids)))
        target = job.id
        request["expectedSha256"] = description_digest(job.description)
    read_only = client.put(f"/api/v1/jobs/{target}/manual-description", json=request)
    assert read_only.status_code == 409 and read_only.json()["error"]["code"] == "manual_description_source_read_only"
    with factory() as session:
        assert session.get(JobORM, ids[0]).description == original
