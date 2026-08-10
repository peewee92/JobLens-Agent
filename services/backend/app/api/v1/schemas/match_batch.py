"""HTTP contract for bounded Phase 5 Batch Match execution."""
from __future__ import annotations

from pydantic import Field

from app.api.v1.schemas.common import CamelCaseModel
from app.application.match_batch_execution import BatchMatchExecutionResult


class BatchMatchExecutionRequest(CamelCaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=50)
    max_ready_jobs: int = Field(default=10, ge=1, le=10)


class BatchMatchExecutionItemResponse(CamelCaseModel):
    job_id: str
    status: str
    blocker_codes: list[str]
    error_code: str | None = None


class BatchMatchExecutionResponse(CamelCaseModel):
    total: int
    succeeded_count: int
    failed_count: int
    deferred_count: int
    input_blocked_count: int
    persistence_blocked_count: int
    items: list[BatchMatchExecutionItemResponse]
    resume_job_ids: list[str]
    execution_complete: bool
    db_writes: int
    provider_calls: int
    trace_runs_created: int
    side_effect_counts_complete: bool

    @classmethod
    def from_result(cls, result: BatchMatchExecutionResult) -> "BatchMatchExecutionResponse":
        return cls(
            total=result.total,
            succeeded_count=result.succeeded_count,
            failed_count=result.failed_count,
            deferred_count=result.deferred_count,
            input_blocked_count=result.input_blocked_count,
            persistence_blocked_count=result.persistence_blocked_count,
            items=[
                BatchMatchExecutionItemResponse(
                    job_id=item.job_id,
                    status=item.status.value,
                    blocker_codes=list(item.blocker_codes),
                    error_code=item.error_code,
                )
                for item in result.items
            ],
            resume_job_ids=list(result.resume_job_ids),
            execution_complete=result.execution_complete,
            db_writes=result.db_writes,
            provider_calls=result.provider_calls,
            trace_runs_created=result.trace_runs_created,
            side_effect_counts_complete=result.side_effect_counts_complete,
        )
