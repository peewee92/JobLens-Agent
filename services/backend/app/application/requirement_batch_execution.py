"""Bounded execution for expanding real Requirement coverage from recommendation candidates."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.application.job_requirements import (
    InvalidRequirementExtractorOutputError,
    JobDescriptionNotExtractableError,
    RequirementExtractorFailedError,
    RequirementExtractorUnavailableError,
)
from app.application.recommendation_coverage import BuildRecommendationCoverageUseCase


class RequirementExtractionRunner(Protocol):
    def execute(self, job_id: str): ...


class RequirementBatchExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    DEFERRED_PROVIDER_UNAVAILABLE = "deferred_provider_unavailable"
    DEFERRED_LIMIT = "deferred_limit"
    NOT_SELECTED = "not_selected"


@dataclass(frozen=True, slots=True)
class RequirementBatchExecutionItem:
    job_id: str
    status: RequirementBatchExecutionStatus
    error_code: str | None = None
    provider_calls: int = 0
    trace_runs_created: int = 0


@dataclass(frozen=True, slots=True)
class RequirementBatchExecutionResult:
    total: int
    succeeded_count: int
    failed_count: int
    deferred_count: int
    provider_unavailable_count: int
    not_selected_count: int
    items: tuple[RequirementBatchExecutionItem, ...]
    resume_job_ids: tuple[str, ...]
    execution_complete: bool
    db_writes: int
    provider_calls: int
    trace_runs_created: int
    side_effect_counts_complete: bool


class ExecuteRequirementBatchUseCase:
    """Run only current recommendation-coverage candidates with a hard per-run bound."""

    MAX_READY_JOBS = 5
    MAX_BATCH_JOBS = 5

    def __init__(
        self,
        *,
        coverage: BuildRecommendationCoverageUseCase,
        extraction_runner: RequirementExtractionRunner,
    ) -> None:
        self._coverage = coverage
        self._extraction_runner = extraction_runner

    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        max_ready_jobs: int = MAX_READY_JOBS,
    ) -> RequirementBatchExecutionResult:
        if not 1 <= max_ready_jobs <= self.MAX_READY_JOBS:
            raise ValueError("max_ready_jobs must be between 1 and 5")
        requested = tuple(dict.fromkeys(job_ids))
        if not requested:
            raise ValueError("batch must contain at least one job")
        if len(requested) > self.MAX_BATCH_JOBS:
            raise ValueError("batch must contain at most 5 jobs")

        coverage = self._coverage.execute()
        selected_ids = {item.job_id for item in coverage.next_analysis_candidates}
        ready_executed = 0
        provider_outage = False
        db_writes = 0
        provider_calls = 0
        trace_runs_created = 0
        side_effect_counts_complete = True
        items: list[RequirementBatchExecutionItem] = []

        for job_id in requested:
            if job_id not in selected_ids:
                items.append(
                    RequirementBatchExecutionItem(
                        job_id=job_id,
                        status=RequirementBatchExecutionStatus.NOT_SELECTED,
                        error_code="not_current_coverage_candidate",
                    )
                )
                continue
            if provider_outage:
                items.append(
                    RequirementBatchExecutionItem(
                        job_id=job_id,
                        status=RequirementBatchExecutionStatus.DEFERRED_PROVIDER_UNAVAILABLE,
                        error_code="provider_unavailable",
                    )
                )
                continue
            if ready_executed >= max_ready_jobs:
                items.append(
                    RequirementBatchExecutionItem(
                        job_id=job_id,
                        status=RequirementBatchExecutionStatus.DEFERRED_LIMIT,
                        error_code="requirement_batch_limit_reached",
                    )
                )
                continue

            ready_executed += 1
            try:
                extraction = self._extraction_runner.execute(job_id)
            except RequirementExtractorUnavailableError as error:
                call_count = int(getattr(error, "provider_calls", 0))
                trace_count = int(bool(getattr(error, "run_id", None)))
                provider_calls += call_count
                trace_runs_created += trace_count
                provider_outage = True
                items.append(
                    RequirementBatchExecutionItem(
                        job_id=job_id,
                        status=RequirementBatchExecutionStatus.PROVIDER_UNAVAILABLE,
                        error_code="requirement_provider_unavailable",
                        provider_calls=call_count,
                        trace_runs_created=trace_count,
                    )
                )
            except (
                RequirementExtractorFailedError,
                InvalidRequirementExtractorOutputError,
                JobDescriptionNotExtractableError,
            ) as error:
                call_count = int(getattr(error, "provider_calls", 0))
                trace_count = int(bool(getattr(error, "run_id", None)))
                provider_calls += call_count
                trace_runs_created += trace_count
                items.append(
                    RequirementBatchExecutionItem(
                        job_id=job_id,
                        status=RequirementBatchExecutionStatus.FAILED,
                        error_code="requirement_extraction_failed",
                        provider_calls=call_count,
                        trace_runs_created=trace_count,
                    )
                )
            except Exception:
                side_effect_counts_complete = False
                items.append(
                    RequirementBatchExecutionItem(
                        job_id=job_id,
                        status=RequirementBatchExecutionStatus.FAILED,
                        error_code="requirement_extraction_failed",
                    )
                )
            else:
                call_count = int(getattr(extraction, "provider_calls", 0))
                provider_calls += call_count
                db_writes += 1
                trace_runs_created += 1
                items.append(
                    RequirementBatchExecutionItem(
                        job_id=job_id,
                        status=RequirementBatchExecutionStatus.SUCCEEDED,
                        provider_calls=call_count,
                        trace_runs_created=1,
                    )
                )

        result_items = tuple(items)
        resume_job_ids = tuple(
            item.job_id
            for item in result_items
            if item.status
            in {
                RequirementBatchExecutionStatus.DEFERRED_LIMIT,
                RequirementBatchExecutionStatus.DEFERRED_PROVIDER_UNAVAILABLE,
            }
        )
        deferred_statuses = {
            RequirementBatchExecutionStatus.DEFERRED_LIMIT,
            RequirementBatchExecutionStatus.DEFERRED_PROVIDER_UNAVAILABLE,
        }
        return RequirementBatchExecutionResult(
            total=len(result_items),
            succeeded_count=sum(item.status is RequirementBatchExecutionStatus.SUCCEEDED for item in result_items),
            failed_count=sum(item.status is RequirementBatchExecutionStatus.FAILED for item in result_items),
            deferred_count=sum(item.status in deferred_statuses for item in result_items),
            provider_unavailable_count=sum(
                item.status is RequirementBatchExecutionStatus.PROVIDER_UNAVAILABLE
                for item in result_items
            ),
            not_selected_count=sum(item.status is RequirementBatchExecutionStatus.NOT_SELECTED for item in result_items),
            items=result_items,
            resume_job_ids=resume_job_ids,
            execution_complete=not resume_job_ids,
            db_writes=db_writes,
            provider_calls=provider_calls,
            trace_runs_created=trace_runs_created,
            side_effect_counts_complete=side_effect_counts_complete,
        )
