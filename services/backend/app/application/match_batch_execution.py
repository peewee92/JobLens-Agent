"""Bounded orchestration for Phase 5 Batch Match execution."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.application.match_batch_planning import (
    BatchMatchPlanStatus,
    PlanBatchMatchUseCase,
)


class MatchReportRunner(Protocol):
    def execute(self, job_id: str): ...


class BatchMatchExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INPUT_BLOCKED = "input_blocked"
    PERSISTENCE_BLOCKED = "persistence_blocked"
    DEFERRED_LIMIT = "deferred_limit"


@dataclass(frozen=True, slots=True)
class BatchMatchExecutionItem:
    job_id: str
    status: BatchMatchExecutionStatus
    blocker_codes: tuple[str, ...] = ()
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class BatchMatchExecutionResult:
    total: int
    succeeded_count: int
    failed_count: int
    deferred_count: int
    input_blocked_count: int
    persistence_blocked_count: int
    items: tuple[BatchMatchExecutionItem, ...]
    resume_job_ids: tuple[str, ...]
    execution_complete: bool
    db_writes: int
    provider_calls: int
    trace_runs_created: int
    side_effect_counts_complete: bool


class ExecuteBatchMatchUseCase:
    """Execute only planner-approved jobs, with a hard per-run ready-job bound."""

    MAX_READY_JOBS = 10
    MAX_BATCH_JOBS = 50

    def __init__(
        self,
        *,
        planner: PlanBatchMatchUseCase,
        report_runner: MatchReportRunner,
    ) -> None:
        self._planner = planner
        self._report_runner = report_runner

    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        max_ready_jobs: int = MAX_READY_JOBS,
    ) -> BatchMatchExecutionResult:
        if not 1 <= max_ready_jobs <= self.MAX_READY_JOBS:
            raise ValueError("max_ready_jobs must be between 1 and 10")
        if len(job_ids) > self.MAX_BATCH_JOBS:
            raise ValueError("batch must contain at most 50 jobs")

        plan = self._planner.execute(job_ids)
        ready_executed = 0
        db_writes = 0
        provider_calls = 0
        trace_runs_created = 0
        side_effect_counts_complete = True
        items: list[BatchMatchExecutionItem] = []

        for planned in plan.items:
            if planned.status is BatchMatchPlanStatus.INPUT_BLOCKED:
                items.append(
                    BatchMatchExecutionItem(
                        job_id=planned.job_id,
                        status=BatchMatchExecutionStatus.INPUT_BLOCKED,
                        blocker_codes=planned.blocker_codes,
                    )
                )
                continue
            if planned.status is BatchMatchPlanStatus.PERSISTENCE_BLOCKED:
                items.append(
                    BatchMatchExecutionItem(
                        job_id=planned.job_id,
                        status=BatchMatchExecutionStatus.PERSISTENCE_BLOCKED,
                        blocker_codes=planned.blocker_codes,
                    )
                )
                continue
            if ready_executed >= max_ready_jobs:
                items.append(
                    BatchMatchExecutionItem(
                        job_id=planned.job_id,
                        status=BatchMatchExecutionStatus.DEFERRED_LIMIT,
                        blocker_codes=("batch_ready_job_limit_reached",),
                    )
                )
                continue

            ready_executed += 1
            try:
                report = self._report_runner.execute(planned.job_id)
            except Exception:
                side_effect_counts_complete = False
                items.append(
                    BatchMatchExecutionItem(
                        job_id=planned.job_id,
                        status=BatchMatchExecutionStatus.FAILED,
                        error_code="match_execution_failed",
                    )
                )
                continue

            db_writes += int(getattr(report, "db_writes", 0))
            provider_calls += int(getattr(report, "provider_calls", 0))
            trace_runs_created += int(getattr(report, "trace_runs_created", 0))
            items.append(
                BatchMatchExecutionItem(
                    job_id=planned.job_id,
                    status=BatchMatchExecutionStatus.SUCCEEDED,
                )
            )

        result_items = tuple(items)
        resume_job_ids = tuple(
            item.job_id
            for item in result_items
            if item.status is BatchMatchExecutionStatus.DEFERRED_LIMIT
        )
        return BatchMatchExecutionResult(
            total=len(result_items),
            succeeded_count=sum(item.status is BatchMatchExecutionStatus.SUCCEEDED for item in result_items),
            failed_count=sum(item.status is BatchMatchExecutionStatus.FAILED for item in result_items),
            deferred_count=sum(item.status is BatchMatchExecutionStatus.DEFERRED_LIMIT for item in result_items),
            input_blocked_count=sum(item.status is BatchMatchExecutionStatus.INPUT_BLOCKED for item in result_items),
            persistence_blocked_count=sum(item.status is BatchMatchExecutionStatus.PERSISTENCE_BLOCKED for item in result_items),
            items=result_items,
            resume_job_ids=resume_job_ids,
            execution_complete=not resume_job_ids,
            db_writes=db_writes,
            provider_calls=provider_calls,
            trace_runs_created=trace_runs_created,
            side_effect_counts_complete=side_effect_counts_complete,
        )
