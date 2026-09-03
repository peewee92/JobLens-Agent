"""HTTP contract for bounded Requirement Analysis execution."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.api.v1.schemas.common import CamelCaseModel
from app.application.requirement_batch_execution import RequirementBatchExecutionResult


class RequirementBatchExecutionRequest(CamelCaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=5)
    max_ready_jobs: int = Field(default=5, ge=1, le=5)
    confirm_live_cost: Literal[True]


class RequirementBatchExecutionItemResponse(CamelCaseModel):
    job_id: str
    status: str
    error_code: str | None = None
    provider_calls: int
    trace_runs_created: int


class RequirementBatchExecutionResponse(CamelCaseModel):
    total: int
    succeeded_count: int
    failed_count: int
    deferred_count: int
    provider_unavailable_count: int
    not_selected_count: int
    items: list[RequirementBatchExecutionItemResponse]
    resume_job_ids: list[str]
    execution_complete: bool
    db_writes: int
    provider_calls: int
    trace_runs_created: int
    side_effect_counts_complete: bool

    @classmethod
    def from_result(cls, result: RequirementBatchExecutionResult) -> "RequirementBatchExecutionResponse":
        return cls(
            total=result.total,
            succeeded_count=result.succeeded_count,
            failed_count=result.failed_count,
            deferred_count=result.deferred_count,
            provider_unavailable_count=result.provider_unavailable_count,
            not_selected_count=result.not_selected_count,
            items=[
                RequirementBatchExecutionItemResponse(
                    job_id=item.job_id,
                    status=item.status.value,
                    error_code=item.error_code,
                    provider_calls=item.provider_calls,
                    trace_runs_created=item.trace_runs_created,
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
