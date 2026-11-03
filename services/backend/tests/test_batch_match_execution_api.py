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
        max_ready_jobs: int = 5,
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
            resume_job_ids=(),
            execution_complete=True,
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
    assert body["resumeJobIds"] == []
    assert body["executionComplete"] is True
    assert use_case.calls == [(("job_1", "job_2"), 2)]


def test_batch_match_execution_api_rejects_more_than_five_ready_jobs_per_run() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_batch_match_execution_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/match-batch",
                json={"jobIds": ["job_1"], "maxReadyJobs": 6},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert use_case.calls == []


def test_batch_match_execution_api_rejects_more_than_fifty_jobs() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_batch_match_execution_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/match-batch",
                json={"jobIds": [f"job_{index}" for index in range(51)], "maxReadyJobs": 5},
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


def test_shared_contract_and_http_request_bounds_match():
    import json
    from pathlib import Path
    from app.api.v1.schemas.match_batch import BatchMatchExecutionRequest
    root = Path(__file__).resolve().parents[3]
    shared = json.loads((root / "packages/contracts/schemas/match-batch-execution-request.schema.json").read_text())
    actual = BatchMatchExecutionRequest.model_json_schema(by_alias=True)
    for field in ("jobIds", "maxReadyJobs"):
        for key in ("minimum", "maximum", "minItems", "maxItems", "default"):
            if key in shared["properties"][field]:
                assert actual["properties"][field][key] == shared["properties"][field][key]
    assert actual["required"] == shared["required"]


def test_http_fifty_jobs_process_five_then_explicitly_resume():
    from types import SimpleNamespace
    from app.application.match_batch_execution import ExecuteBatchMatchUseCase
    from app.application.match_batch_planning import BatchMatchPlan, BatchMatchPlanItem, BatchMatchPlanStatus

    class Planner:
        def execute(self, ids):
            return BatchMatchPlan(total=len(ids), ready_count=len(ids), input_blocked_count=0,
                persistence_blocked_count=0, items=tuple(BatchMatchPlanItem(i, BatchMatchPlanStatus.READY, ()) for i in ids))
    class Runner:
        def __init__(self): self.calls = []
        def execute(self, job_id):
            self.calls.append(job_id)
            return SimpleNamespace(db_writes=1, provider_calls=0, trace_runs_created=0)
    runner = Runner()
    app.dependency_overrides[get_batch_match_execution_use_case] = lambda: ExecuteBatchMatchUseCase(planner=Planner(), report_runner=runner)
    try:
        with TestClient(app) as client:
            first = client.post("/api/v1/match-batch", json={"jobIds": [f"job_{i}" for i in range(50)]})
            assert first.status_code == 200
            payload = first.json()
            assert payload["succeededCount"] == 5
            assert len(payload["resumeJobIds"]) == 45
            assert len(runner.calls) == 5
            second = client.post("/api/v1/match-batch", json={"jobIds": payload["resumeJobIds"]})
            assert second.status_code == 200
            assert second.json()["succeededCount"] == 5
            assert len(second.json()["resumeJobIds"]) == 40
            assert len(runner.calls) == 10
    finally:
        app.dependency_overrides.pop(get_batch_match_execution_use_case, None)
