"""HTTP contract tests for bounded Phase 5 Batch Match execution."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_batch_match_execution_use_case
from app.application.match_batch_execution import (
    BatchMatchExecutionItem,
    BatchMatchExecutionResult,
    BatchMatchExecutionStatus,
)
from app.main import app


class _UseCase:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        max_ready_jobs: int = 10,
    ) -> BatchMatchExecutionResult:
        self.calls.append((job_ids, max_ready_jobs))
        return BatchMatchExecutionResult(
            total=2,
            succeeded_count=1,
            failed_count=0,
            deferred_count=0,
            input_blocked_count=1,
            persistence_blocked_count=0,
            items=(
                BatchMatchExecutionItem(
                    job_id="job_1",
                    status=BatchMatchExecutionStatus.SUCCEEDED,
                ),
                BatchMatchExecutionItem(
                    job_id="job_2",
                    status=BatchMatchExecutionStatus.INPUT_BLOCKED,
                    blocker_codes=("requirement_release_not_ready",),
                ),
            ),
            db_writes=1,
            provider_calls=1,
            trace_runs_created=1,
            side_effect_counts_complete=True,
        )


def test_batch_match_execution_api_runs_bounded_ready_jobs() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_batch_match_execution_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/match-batch",
                json={"jobIds": ["job_1", "job_2"], "maxReadyJobs": 2},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["succeededCount"] == 1
    assert body["inputBlockedCount"] == 1
    assert body["items"][1]["blockerCodes"] == ["requirement_release_not_ready"]
    assert body["dbWrites"] == 1
    assert body["providerCalls"] == 1
    assert body["traceRunsCreated"] == 1
    assert body["sideEffectCountsComplete"] is True
    assert use_case.calls == [(("job_1", "job_2"), 2)]


def test_batch_match_execution_api_rejects_more_than_ten_ready_jobs_per_run() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_batch_match_execution_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/match-batch",
                json={"jobIds": ["job_1"], "maxReadyJobs": 11},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert use_case.calls == []


def test_batch_match_execution_api_requires_at_least_one_job_id() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/match-batch",
            json={"jobIds": [], "maxReadyJobs": 1},
        )

    assert response.status_code == 422


def test_openapi_registers_batch_match_execution_as_post() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/match-batch"]["post"]

    assert "requestBody" in operation
    assert "200" in operation["responses"]
