"""HTTP integration tests for persisted Requirement Eval runs."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_requirement_eval_query_repository
from app.db.base import Base
from app.evals import (
    RequirementEvalMode,
    RunRequirementEvalUseCase,
    load_job_requirement_eval_cases,
)
from app.llm import FixtureJobRequirementExtractor
from app.main import app
from app.repositories import (
    SqlAlchemyRequirementEvalQueryRepository,
    SqlAlchemyRequirementEvalUnitOfWork,
    SqlAlchemyTraceUnitOfWork,
)
from app.workflows import ExtractJobRequirementsWorkflow

DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "requirement-extraction"
    / "requirement-extraction-v1.jsonl"
)


@pytest.fixture
def api_environment(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'requirement-eval-api.db'}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.dependency_overrides[get_requirement_eval_query_repository] = lambda: (
        SqlAlchemyRequirementEvalQueryRepository(factory)
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed_run(factory: sessionmaker[Session], baseline_run_id: str | None = None):
    extractor = FixtureJobRequirementExtractor()
    workflow = ExtractJobRequirementsWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(factory),
    )
    repository = SqlAlchemyRequirementEvalQueryRepository(factory)
    return RunRequirementEvalUseCase(
        workflow=workflow,
        eval_uow_factory=lambda: SqlAlchemyRequirementEvalUnitOfWork(factory),
        query_repository=repository,
        dataset_version="requirement-extraction-v1",
        mode=RequirementEvalMode.FIXTURE,
        provider="fixture",
        model=extractor.model_name,
    ).execute(
        load_job_requirement_eval_cases(DATASET),
        baseline_run_id=baseline_run_id,
    )


def test_list_and_detail_requirement_eval_runs(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    baseline = _seed_run(factory)
    current = _seed_run(factory, baseline.summary.id)

    list_response = client.get("/api/v1/requirement-evals?limit=1&offset=0")
    assert list_response.status_code == 200
    page = list_response.json()
    assert page["total"] == 2
    assert page["limit"] == 1
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] == current.summary.id
    assert page["items"][0]["releaseEligible"] is False
    assert page["items"][0]["createdAt"].endswith(("Z", "+00:00"))

    detail_response = client.get(
        f"/api/v1/requirement-evals/{current.summary.id}"
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["summary"]["gateVersion"] == "requirement-eval-gate-v1"
    assert detail["summary"]["gatePassed"] is True
    assert detail["comparison"]["baselineRunId"] == baseline.summary.id
    assert detail["comparison"]["capabilityRecallDelta"] == 0.0
    assert len(detail["cases"]) == 10
    assert all(item["traceRunId"].startswith("run_") for item in detail["cases"])
    serialized = detail_response.text
    assert "description" not in serialized
    assert "originalText" not in serialized


def test_missing_requirement_eval_run_returns_structured_404(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    response = client.get("/api/v1/requirement-evals/reqeval_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "requirement_eval_run_not_found"


def test_requirement_eval_openapi_contract_is_registered(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert paths["/api/v1/requirement-evals"]["get"]
    assert paths["/api/v1/requirement-evals/{eval_run_id}"]["get"]["responses"]["404"]
