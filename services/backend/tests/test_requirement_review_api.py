"""HTTP integration tests for Requirement manual quality review batches."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    get_requirement_review_query_repository,
    get_requirement_review_uow_factory,
)
from app.db.base import Base
from app.db.models import (
    JobORM,
    JobRequirementExtractionORM,
    JobRequirementORM,
    RequirementReviewBatchFinalDecisionORM,
    TraceSpanORM,
)
from app.main import app
from app.repositories import (
    SqlAlchemyRequirementReviewQueryRepository,
    SqlAlchemyRequirementReviewUnitOfWork,
)


@pytest.fixture
def api_environment(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'requirement-review-api.db'}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.dependency_overrides[get_requirement_review_query_repository] = lambda: (
        SqlAlchemyRequirementReviewQueryRepository(factory)
    )
    app.dependency_overrides[get_requirement_review_uow_factory] = lambda: (
        lambda: SqlAlchemyRequirementReviewUnitOfWork(factory)
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed_extraction(factory: sessionmaker[Session], index: int) -> str:
    job_id = f"job_review_api_{index}"
    trace_id = f"run_review_api_{index}"
    extraction_id = f"reqrun_review_api_{index}"
    created_at = datetime(2026, 8, 3, 13, index, tzinfo=timezone.utc)
    description = "负责 Python、FastAPI 与 Agent 工作流开发，要求输出可追溯。"
    with factory() as session:
        session.add(
            JobORM(
                id=job_id,
                canonical_key=f"review-api:{index}",
                title=f"Agent Engineer {index}",
                company=f"API Company {index}",
                description=description,
                skills=["Python", "FastAPI", "Agent"],
            )
        )
        session.add(
            TraceSpanORM(
                id=trace_id,
                capability="requirement_extraction",
                version="requirement-extractor-v1",
                model="api-quality-model",
                prompt_version="requirement-extraction-v1",
                input_refs={"jobId": job_id},
                output={"requirements": []},
                latency_ms=8,
                input_tokens=10,
                output_tokens=5,
                error=None,
                created_at=created_at,
            )
        )
        session.flush()
        extraction = JobRequirementExtractionORM(
            id=extraction_id,
            job_id=job_id,
            input_hash=sha256(description.encode("utf-8")).hexdigest(),
            description_characters=55,
            extractor_version="requirement-extractor-v1",
            provider="openai",
            model="api-quality-model",
            prompt_version="requirement-extraction-v1",
            trace_run_id=trace_id,
            requirement_count=1,
            created_at=created_at,
        )
        extraction.requirements.append(
            JobRequirementORM(
                id=f"req_review_api_{index}",
                job_id=job_id,
                requirement_index=0,
                type="skill",
                original_text="要求 Python、FastAPI 与 Agent 工作流开发",
                normalized_capability="Python",
                importance="must_have",
                evidence_span="要求 Python、FastAPI 与 Agent 工作流开发",
                confidence=0.9,
                extractor_version="requirement-extractor-v1",
                created_at=created_at,
            )
        )
        session.add(extraction)
        session.commit()
    return extraction_id


def _create_completed_batch(
    client: TestClient,
    factory: sessionmaker[Session],
    *,
    start_index: int,
    rejected_indexes: set[int] | None = None,
) -> dict:
    rejected_indexes = rejected_indexes or set()
    extraction_ids = [
        _seed_extraction(factory, start_index + index)
        for index in range(20)
    ]
    created = client.post(
        "/api/v1/requirement-review-batches",
        json={
            "title": f"Formal API batch {start_index}",
            "reviewer": "will",
            "extractionIds": extraction_ids,
        },
    )
    assert created.status_code == 201, created.text
    detail = created.json()
    batch_id = detail["summary"]["id"]
    for index, case in enumerate(detail["cases"]):
        rejected = index in rejected_indexes
        response = client.post(
            f"/api/v1/requirement-review-batches/{batch_id}/cases/{case['id']}/review",
            json={
                "decision": "rejected" if rejected else "accepted",
                "issueCodes": ["missing_requirement"] if rejected else [],
                "notes": (
                    "The frozen extraction omits one grounded Requirement from this JD."
                    if rejected
                    else "The frozen extraction is grounded in the reviewed JD evidence."
                ),
            },
        )
        assert response.status_code == 201, response.text
    completed = client.get(
        f"/api/v1/requirement-review-batches/{batch_id}"
    )
    assert completed.status_code == 200
    return completed.json()


def test_candidate_create_detail_and_review_flow(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    extraction_ids = [_seed_extraction(factory, index) for index in range(2)]

    candidates = client.get("/api/v1/requirement-review-batches/candidates")
    assert candidates.status_code == 200
    assert candidates.json()["total"] == 2
    assert {item["extractionId"] for item in candidates.json()["items"]} == set(
        extraction_ids
    )

    created = client.post(
        "/api/v1/requirement-review-batches",
        json={
            "title": "API manual quality review",
            "reviewer": "will",
            "extractionIds": extraction_ids,
        },
    )
    assert created.status_code == 201, created.text
    detail = created.json()
    batch_id = detail["summary"]["id"]
    assert detail["summary"]["sampleSize"] == 2
    assert detail["summary"]["formalEvidenceEligible"] is False
    assert detail["summary"]["finalDecision"] is None
    assert detail["summary"]["matchReleaseEligible"] is False
    assert detail["finalDecision"] is None
    assert detail["cases"][0]["description"]
    assert detail["cases"][0]["requirements"][0]["evidenceSpan"]
    assert detail["cases"][0]["traceRunId"].startswith("run_review_api_")

    case_id = detail["cases"][0]["id"]
    reviewed = client.post(
        f"/api/v1/requirement-review-batches/{batch_id}/cases/{case_id}/review",
        json={
            "decision": "rejected",
            "issueCodes": ["wrong_normalization"],
            "notes": "The normalized capability does not represent the full JD requirement.",
        },
    )
    assert reviewed.status_code == 201, reviewed.text
    assert reviewed.json()["decision"] == "rejected"

    refreshed = client.get(f"/api/v1/requirement-review-batches/{batch_id}")
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["summary"]["reviewedCount"] == 1
    assert body["summary"]["rejectedCount"] == 1
    assert body["issueCodeCounts"] == {"wrong_normalization": 1}


def test_invalid_batch_and_review_requests_return_stable_422(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    extraction_id = _seed_extraction(factory, 3)

    duplicate = client.post(
        "/api/v1/requirement-review-batches",
        json={
            "title": "duplicate",
            "reviewer": "will",
            "extractionIds": [extraction_id, extraction_id],
        },
    )
    assert duplicate.status_code == 422
    assert duplicate.json()["error"]["code"] == "invalid_requirement_review_batch"

    created = client.post(
        "/api/v1/requirement-review-batches",
        json={
            "title": "review truth table",
            "reviewer": "will",
            "extractionIds": [extraction_id],
        },
    ).json()
    batch_id = created["summary"]["id"]
    case_id = created["cases"][0]["id"]

    invalid_review = client.post(
        f"/api/v1/requirement-review-batches/{batch_id}/cases/{case_id}/review",
        json={
            "decision": "rejected",
            "issueCodes": [],
            "notes": "A rejected case requires at least one structured issue code.",
        },
    )
    assert invalid_review.status_code == 422
    assert invalid_review.json()["error"]["code"] == "invalid_requirement_case_review"


def test_duplicate_case_review_returns_409(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    extraction_id = _seed_extraction(factory, 4)
    created = client.post(
        "/api/v1/requirement-review-batches",
        json={
            "title": "immutable review",
            "reviewer": "will",
            "extractionIds": [extraction_id],
        },
    ).json()
    batch_id = created["summary"]["id"]
    case_id = created["cases"][0]["id"]
    payload = {
        "decision": "accepted",
        "issueCodes": [],
        "notes": "The extraction is grounded and complete for this reviewed case.",
    }

    first = client.post(
        f"/api/v1/requirement-review-batches/{batch_id}/cases/{case_id}/review",
        json=payload,
    )
    second = client.post(
        f"/api/v1/requirement-review-batches/{batch_id}/cases/{case_id}/review",
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "requirement_review_case_already_reviewed"


def test_missing_batch_and_case_return_distinct_404_codes(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    extraction_id = _seed_extraction(factory, 5)
    created = client.post(
        "/api/v1/requirement-review-batches",
        json={
            "title": "missing cases",
            "reviewer": "will",
            "extractionIds": [extraction_id],
        },
    ).json()
    batch_id = created["summary"]["id"]
    payload = {
        "decision": "accepted",
        "issueCodes": [],
        "notes": "This payload is valid but the resource identifier is missing.",
    }

    missing_batch = client.get("/api/v1/requirement-review-batches/reqreviewbatch_missing")
    missing_case = client.post(
        f"/api/v1/requirement-review-batches/{batch_id}/cases/reqreviewcase_missing/review",
        json=payload,
    )

    assert missing_batch.status_code == 404
    assert missing_batch.json()["error"]["code"] == "requirement_review_batch_not_found"
    assert missing_case.status_code == 404
    assert missing_case.json()["error"]["code"] == "requirement_review_case_not_found"


def test_final_decision_api_and_accepted_baseline_lifecycle(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    missing = client.get(
        "/api/v1/requirement-review-batches/accepted-baseline"
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == (
        "accepted_requirement_review_baseline_not_found"
    )

    completed = _create_completed_batch(
        client,
        factory,
        start_index=20,
        rejected_indexes={3},
    )
    batch_id = completed["summary"]["id"]
    assert completed["summary"]["formalEvidenceEligible"] is True
    assert completed["summary"]["matchReleaseEligible"] is False

    accepted = client.post(
        f"/api/v1/requirement-review-batches/{batch_id}/final-decision",
        json={
            "decision": "accept_for_match",
            "reviewer": "will",
            "notes": (
                "I reviewed all twenty frozen Cases and accept this exact model cohort "
                "as the current Requirement baseline for the first Match slice."
            ),
        },
    )
    assert accepted.status_code == 201, accepted.text
    decision = accepted.json()
    assert decision["decision"] == "accept_for_match"
    assert decision["acceptedCount"] == 19
    assert decision["rejectedCount"] == 1
    assert decision["issueCodeCounts"] == {"missing_requirement": 1}
    assert len(decision["evidenceFingerprint"]) == 64

    duplicate = client.post(
        f"/api/v1/requirement-review-batches/{batch_id}/final-decision",
        json={
            "decision": "reject_for_match",
            "reviewer": "will",
            "notes": "A second final decision must not overwrite the immutable first decision.",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == (
        "requirement_review_batch_final_decision_already_exists"
    )

    refreshed = client.get(
        f"/api/v1/requirement-review-batches/{batch_id}"
    ).json()
    assert refreshed["summary"]["finalDecision"] == "accept_for_match"
    assert refreshed["summary"]["matchReleaseEligible"] is True
    assert refreshed["finalDecision"]["id"] == decision["id"]

    baseline = client.get(
        "/api/v1/requirement-review-batches/accepted-baseline"
    )
    assert baseline.status_code == 200
    assert baseline.json()["batch"]["id"] == batch_id
    assert baseline.json()["decision"]["id"] == decision["id"]

    with factory() as session:
        job = session.get(JobORM, "job_review_api_20")
        assert job is not None
        job.description = (job.description or "") + " 新增必须掌握生产级评测治理。"
        session.commit()

    stale = client.get(
        f"/api/v1/requirement-review-batches/{batch_id}"
    ).json()
    assert stale["summary"]["staleCaseCount"] == 1
    assert stale["summary"]["matchReleaseEligible"] is False
    assert stale["finalDecision"]["id"] == decision["id"]
    missing_after_stale = client.get(
        "/api/v1/requirement-review-batches/accepted-baseline"
    )
    assert missing_after_stale.status_code == 404


def test_incomplete_final_decision_returns_422_without_db_write(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    extraction_id = _seed_extraction(factory, 45)
    created = client.post(
        "/api/v1/requirement-review-batches",
        json={
            "title": "incomplete final API decision",
            "reviewer": "will",
            "extractionIds": [extraction_id],
        },
    ).json()

    response = client.post(
        f"/api/v1/requirement-review-batches/{created['summary']['id']}/final-decision",
        json={
            "decision": "accept_for_match",
            "reviewer": "will",
            "notes": "This practice Batch must not authorize the production Match fact baseline.",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == (
        "invalid_requirement_review_batch_final_decision"
    )
    with factory() as session:
        assert int(
            session.scalar(
                select(func.count()).select_from(
                    RequirementReviewBatchFinalDecisionORM
                )
            )
            or 0
        ) == 0


def test_requirement_review_openapi_contract_is_registered(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert paths["/api/v1/requirement-review-batches/candidates"]["get"]
    assert paths["/api/v1/requirement-review-batches"]["post"]["responses"]["201"]
    assert paths["/api/v1/requirement-review-batches/{batch_id}"]["get"]
    assert paths["/api/v1/requirement-review-batches/accepted-baseline"]["get"]
    final_decision = paths[
        "/api/v1/requirement-review-batches/{batch_id}/final-decision"
    ]["post"]
    assert final_decision["responses"]["201"]
    assert final_decision["responses"]["409"]
    assert final_decision["responses"]["422"]
    review = paths[
        "/api/v1/requirement-review-batches/{batch_id}/cases/{case_id}/review"
    ]["post"]
    assert review["responses"]["201"]
    assert review["responses"]["409"]
    assert review["responses"]["422"]
