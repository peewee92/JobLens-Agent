from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_requirement_batch_execution_use_case
from app.application.requirement_batch_execution import (
    RequirementBatchExecutionItem,
    RequirementBatchExecutionResult,
    RequirementBatchExecutionStatus,
)
from app.main import app


class _UseCase:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def execute(self, job_ids: tuple[str, ...], *, max_ready_jobs: int):
        self.calls.append((job_ids, max_ready_jobs))
        return RequirementBatchExecutionResult(
            total=2,
            succeeded_count=1,
            failed_count=0,
            deferred_count=1,
            provider_unavailable_count=0,
            not_selected_count=0,
            items=(
                RequirementBatchExecutionItem(
                    job_id="job_1",
                    status=RequirementBatchExecutionStatus.SUCCEEDED,
                    provider_calls=1,
                    trace_runs_created=1,
                ),
                RequirementBatchExecutionItem(
                    job_id="job_2",
                    status=RequirementBatchExecutionStatus.DEFERRED_LIMIT,
                    error_code="requirement_batch_limit_reached",
                ),
            ),
            resume_job_ids=("job_2",),
            execution_complete=False,
            db_writes=1,
            provider_calls=1,
            trace_runs_created=1,
            side_effect_counts_complete=True,
        )


def test_requirement_batch_api_exposes_bounded_execution_contract() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_requirement_batch_execution_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/requirement-batch",
                json={"jobIds": ["job_1", "job_2"], "maxReadyJobs": 1},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["succeededCount"] == 1
    assert body["deferredCount"] == 1
    assert body["resumeJobIds"] == ["job_2"]
    assert body["dbWrites"] == 1
    assert body["providerCalls"] == 1
    assert body["traceRunsCreated"] == 1
    assert use_case.calls == [(('job_1', 'job_2'), 1)]


def test_requirement_batch_api_rejects_more_than_five_jobs() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/requirement-batch",
            json={"jobIds": [f"job_{index}" for index in range(6)]},
        )
    assert response.status_code == 422


def test_openapi_registers_requirement_batch_as_explicit_post() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/requirement-batch"]["post"]
    assert "requestBody" in operation
