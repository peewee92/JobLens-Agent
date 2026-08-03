"""HTTP integration tests for Requirement Eval Review and accepted baseline."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    get_requirement_eval_query_repository,
    get_requirement_eval_review_uow_factory,
)
from app.application.job_requirements import (
    JobRequirementExtractionOutput,
    JobRequirementExtractorResult,
)
from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
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
    SqlAlchemyRequirementEvalReviewUnitOfWork,
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
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'requirement-eval-review-api.db'}"
    )

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
    app.dependency_overrides[get_requirement_eval_review_uow_factory] = lambda: (
        lambda: SqlAlchemyRequirementEvalReviewUnitOfWork(factory)
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


class DegradedRequirementExtractor(AbstractJobRequirementExtractor):
    def __init__(self) -> None:
        self._fixture = FixtureJobRequirementExtractor()

    @property
    def model_name(self) -> str:
        return "degraded-requirement-extractor"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        result = self._fixture.extract(description)
        return JobRequirementExtractorResult(
            output=JobRequirementExtractionOutput(
                requirements=result.output.requirements[:1]
            ),
            model=self.model_name,
        )


def _seed_run(
    factory: sessionmaker[Session],
    *,
    mode: RequirementEvalMode,
    provider: str,
    extractor: AbstractJobRequirementExtractor | None = None,
):
    extractor = extractor or FixtureJobRequirementExtractor()
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
        mode=mode,
        provider=provider,
        model=extractor.model_name,
    ).execute(load_job_requirement_eval_cases(DATASET))


def _review_payload(decision: str = "accepted") -> dict[str, str]:
    return {
        "decision": decision,
        "reviewer": "local-reviewer",
        "notes": "Reviewed every Requirement case and linked Trace before this decision.",
    }


def test_accept_live_run_and_query_current_requirement_baseline(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    run = _seed_run(
        factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
    )

    review_response = client.post(
        f"/api/v1/requirement-evals/{run.summary.id}/review",
        json=_review_payload(),
    )

    assert review_response.status_code == 201
    review = review_response.json()
    assert review["id"].startswith("reqreview_")
    assert review["evalRunId"] == run.summary.id
    assert review["decision"] == "accepted"
    assert review["reviewedAt"].endswith(("Z", "+00:00"))

    baseline_response = client.get(
        "/api/v1/requirement-evals/baseline/accepted"
    )
    assert baseline_response.status_code == 200
    baseline = baseline_response.json()
    assert baseline["review"]["id"] == review["id"]
    assert baseline["run"]["id"] == run.summary.id
    assert baseline["run"]["mode"] == "live"
    assert baseline["run"]["releaseEligible"] is True
    assert "description" not in baseline_response.text
    assert "originalText" not in baseline_response.text
    assert "evidenceSpan" not in baseline_response.text

    detail_response = client.get(
        f"/api/v1/requirement-evals/{run.summary.id}"
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["review"]["id"] == review["id"]


def test_fixture_review_returns_stable_422(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    run = _seed_run(
        factory,
        mode=RequirementEvalMode.FIXTURE,
        provider="fixture",
    )

    response = client.post(
        f"/api/v1/requirement-evals/{run.summary.id}/review",
        json=_review_payload("rejected"),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_requirement_eval_review"


def test_gate_failed_live_run_can_be_rejected_and_is_not_baseline(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    run = _seed_run(
        factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
        extractor=DegradedRequirementExtractor(),
    )

    accept_response = client.post(
        f"/api/v1/requirement-evals/{run.summary.id}/review",
        json=_review_payload(),
    )
    assert accept_response.status_code == 422
    assert accept_response.json()["error"]["code"] == "invalid_requirement_eval_review"

    reject_response = client.post(
        f"/api/v1/requirement-evals/{run.summary.id}/review",
        json=_review_payload("rejected"),
    )
    assert reject_response.status_code == 201
    assert reject_response.json()["decision"] == "rejected"

    baseline_response = client.get(
        "/api/v1/requirement-evals/baseline/accepted"
    )
    assert baseline_response.status_code == 404
    assert (
        baseline_response.json()["error"]["code"]
        == "accepted_requirement_eval_baseline_not_found"
    )


def test_duplicate_review_returns_structured_409(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    run = _seed_run(
        factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
    )
    first = client.post(
        f"/api/v1/requirement-evals/{run.summary.id}/review",
        json=_review_payload(),
    )
    second = client.post(
        f"/api/v1/requirement-evals/{run.summary.id}/review",
        json=_review_payload("rejected"),
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert (
        second.json()["error"]["code"]
        == "requirement_eval_run_already_reviewed"
    )


def test_missing_baseline_and_missing_run_return_distinct_404_codes(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    baseline = client.get("/api/v1/requirement-evals/baseline/accepted")
    missing_run = client.post(
        "/api/v1/requirement-evals/reqeval_missing/review",
        json=_review_payload(),
    )

    assert baseline.status_code == 404
    assert (
        baseline.json()["error"]["code"]
        == "accepted_requirement_eval_baseline_not_found"
    )
    assert missing_run.status_code == 404
    assert (
        missing_run.json()["error"]["code"]
        == "requirement_eval_run_not_found"
    )


def test_invalid_review_notes_return_stable_422(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    run = _seed_run(
        factory,
        mode=RequirementEvalMode.LIVE,
        provider="simulated-live",
    )

    response = client.post(
        f"/api/v1/requirement-evals/{run.summary.id}/review",
        json={"decision": "accepted", "reviewer": "reviewer", "notes": "short"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_requirement_eval_review"


def test_requirement_eval_review_openapi_contract_is_registered(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert paths["/api/v1/requirement-evals/baseline/accepted"]["get"]["responses"]["404"]
    review_operation = paths[
        "/api/v1/requirement-evals/{eval_run_id}/review"
    ]["post"]
    assert review_operation["responses"]["201"]
    assert review_operation["responses"]["409"]
    assert review_operation["responses"]["422"]
