"""Bounded Phase 5 Batch Match execution orchestration tests."""
from types import SimpleNamespace
from unittest.mock import Mock

from app.application.match_batch_execution import (
    BatchMatchExecutionStatus,
    ExecuteBatchMatchUseCase,
)
from app.application.match_batch_planning import (
    BatchMatchPlan,
    BatchMatchPlanItem,
    BatchMatchPlanStatus,
)


def _plan(*items: BatchMatchPlanItem) -> BatchMatchPlan:
    return BatchMatchPlan(
        total=len(items),
        ready_count=sum(item.status is BatchMatchPlanStatus.READY for item in items),
        input_blocked_count=sum(item.status is BatchMatchPlanStatus.INPUT_BLOCKED for item in items),
        persistence_blocked_count=sum(item.status is BatchMatchPlanStatus.PERSISTENCE_BLOCKED for item in items),
        items=items,
    )


def test_batch_execute_runs_only_ready_jobs_and_preserves_plan_blockers() -> None:
    planner = Mock()
    planner.execute.return_value = _plan(
        BatchMatchPlanItem("job_a", BatchMatchPlanStatus.READY, ()),
        BatchMatchPlanItem("job_b", BatchMatchPlanStatus.INPUT_BLOCKED, ("requirement_not_ready",)),
        BatchMatchPlanItem("job_c", BatchMatchPlanStatus.PERSISTENCE_BLOCKED, ("match_report_persistence_not_ready",)),
    )
    runner = Mock()
    runner.execute.return_value = SimpleNamespace(db_writes=1, provider_calls=1, trace_runs_created=1)

    result = ExecuteBatchMatchUseCase(planner=planner, report_runner=runner).execute(("job_a", "job_b", "job_c"), max_ready_jobs=10)

    runner.execute.assert_called_once_with("job_a")
    assert tuple(item.status for item in result.items) == (
        BatchMatchExecutionStatus.SUCCEEDED,
        BatchMatchExecutionStatus.INPUT_BLOCKED,
        BatchMatchExecutionStatus.PERSISTENCE_BLOCKED,
    )
    assert result.succeeded_count == 1
    assert result.failed_count == 0
    assert result.db_writes == 1
    assert result.provider_calls == 1
    assert result.trace_runs_created == 1


def test_batch_execute_hard_limits_ready_work_and_marks_remainder_deferred() -> None:
    planner = Mock()
    planner.execute.return_value = _plan(
        *(BatchMatchPlanItem(f"job_{index}", BatchMatchPlanStatus.READY, ()) for index in range(12))
    )
    runner = Mock()
    runner.execute.return_value = SimpleNamespace(db_writes=1, provider_calls=1, trace_runs_created=1)

    result = ExecuteBatchMatchUseCase(planner=planner, report_runner=runner).execute(tuple(f"job_{index}" for index in range(12)), max_ready_jobs=10)

    assert runner.execute.call_count == 10
    assert result.succeeded_count == 10
    assert result.deferred_count == 2
    assert result.provider_calls == 10
    assert all(item.status is BatchMatchExecutionStatus.DEFERRED_LIMIT for item in result.items[-2:])


def test_batch_execute_isolates_one_job_failure_and_continues_within_bound() -> None:
    planner = Mock()
    planner.execute.return_value = _plan(
        BatchMatchPlanItem("job_a", BatchMatchPlanStatus.READY, ()),
        BatchMatchPlanItem("job_b", BatchMatchPlanStatus.READY, ()),
    )
    runner = Mock()
    runner.execute.side_effect = [RuntimeError("provider failed"), SimpleNamespace(db_writes=1, provider_calls=0, trace_runs_created=0)]

    result = ExecuteBatchMatchUseCase(planner=planner, report_runner=runner).execute(("job_a", "job_b"), max_ready_jobs=10)

    assert result.items[0].status is BatchMatchExecutionStatus.FAILED
    assert result.items[0].error_code == "match_execution_failed"
    assert result.items[1].status is BatchMatchExecutionStatus.SUCCEEDED
    assert result.failed_count == 1
    assert result.succeeded_count == 1
    assert result.side_effect_counts_complete is False


def test_batch_execute_rejects_bounds_above_ten_before_planning() -> None:
    planner = Mock()
    runner = Mock()

    try:
        ExecuteBatchMatchUseCase(planner=planner, report_runner=runner).execute(("job_a",), max_ready_jobs=11)
    except ValueError as error:
        assert "between 1 and 10" in str(error)
    else:
        raise AssertionError("expected ValueError")

    planner.execute.assert_not_called()
    runner.execute.assert_not_called()
