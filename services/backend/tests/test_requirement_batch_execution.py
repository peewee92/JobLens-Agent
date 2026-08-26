from __future__ import annotations

from types import SimpleNamespace

from app.application.job_requirements import (
    RequirementExtractorFailedError,
    RequirementExtractorUnavailableError,
)
from app.application.requirement_batch_execution import (
    ExecuteRequirementBatchUseCase,
    RequirementBatchExecutionStatus,
)


class _Coverage:
    def __init__(self, job_ids: tuple[str, ...]) -> None:
        self.job_ids = job_ids

    def execute(self):
        return SimpleNamespace(
            next_analysis_candidates=tuple(
                SimpleNamespace(job_id=job_id) for job_id in self.job_ids
            )
        )


class _Runner:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def execute(self, job_id: str):
        self.calls.append(job_id)
        outcome = self.outcomes.get(job_id, SimpleNamespace(provider_calls=1))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_requirement_batch_runs_only_current_coverage_candidates_with_hard_bound() -> None:
    runner = _Runner({})
    result = ExecuteRequirementBatchUseCase(
        coverage=_Coverage(("job_1", "job_2", "job_3")),
        extraction_runner=runner,
    ).execute(("job_1", "job_other", "job_2", "job_3"), max_ready_jobs=2)

    assert runner.calls == ["job_1", "job_2"]
    assert tuple(item.status for item in result.items) == (
        RequirementBatchExecutionStatus.SUCCEEDED,
        RequirementBatchExecutionStatus.NOT_SELECTED,
        RequirementBatchExecutionStatus.SUCCEEDED,
        RequirementBatchExecutionStatus.DEFERRED_LIMIT,
    )
    assert result.succeeded_count == 2
    assert result.not_selected_count == 1
    assert result.deferred_count == 1
    assert result.resume_job_ids == ("job_3",)
    assert result.db_writes == 2
    assert result.provider_calls == 2
    assert result.trace_runs_created == 2
    assert result.side_effect_counts_complete is True


def test_requirement_batch_stops_after_provider_unavailable_and_defers_remaining_candidates() -> None:
    outage = RequirementExtractorUnavailableError(
        "provider unavailable",
        run_id="run_1",
        status_code=503,
        provider_calls=1,
    )
    runner = _Runner({"job_1": outage})
    result = ExecuteRequirementBatchUseCase(
        coverage=_Coverage(("job_1", "job_2", "job_3")),
        extraction_runner=runner,
    ).execute(("job_1", "job_2", "job_3"))

    assert runner.calls == ["job_1"]
    assert tuple(item.status for item in result.items) == (
        RequirementBatchExecutionStatus.PROVIDER_UNAVAILABLE,
        RequirementBatchExecutionStatus.DEFERRED_PROVIDER_UNAVAILABLE,
        RequirementBatchExecutionStatus.DEFERRED_PROVIDER_UNAVAILABLE,
    )
    assert result.provider_unavailable_count == 1
    assert result.deferred_count == 2
    assert result.resume_job_ids == ("job_2", "job_3")
    assert result.db_writes == 0
    assert result.provider_calls == 1
    assert result.trace_runs_created == 1
    assert result.side_effect_counts_complete is True


def test_requirement_batch_keeps_known_case_failure_isolated_and_continues() -> None:
    failure = RequirementExtractorFailedError(
        "invalid structured output",
        run_id="run_fail",
        provider_calls=1,
    )
    runner = _Runner({"job_1": failure, "job_2": SimpleNamespace(provider_calls=2)})
    result = ExecuteRequirementBatchUseCase(
        coverage=_Coverage(("job_1", "job_2")),
        extraction_runner=runner,
    ).execute(("job_1", "job_2"))

    assert runner.calls == ["job_1", "job_2"]
    assert result.failed_count == 1
    assert result.succeeded_count == 1
    assert result.db_writes == 1
    assert result.provider_calls == 3
    assert result.trace_runs_created == 2
    assert result.side_effect_counts_complete is True


def test_requirement_batch_deduplicates_input_and_rejects_oversized_batches() -> None:
    runner = _Runner({})
    use_case = ExecuteRequirementBatchUseCase(
        coverage=_Coverage(("job_1", "job_2")),
        extraction_runner=runner,
    )
    result = use_case.execute(("job_1", "job_1", "job_2"))
    assert runner.calls == ["job_1", "job_2"]
    assert result.total == 2

    try:
        use_case.execute(tuple(f"job_{index}" for index in range(6)))
    except ValueError as error:
        assert "at most 5" in str(error)
    else:
        raise AssertionError("expected oversized Requirement batch to fail")
