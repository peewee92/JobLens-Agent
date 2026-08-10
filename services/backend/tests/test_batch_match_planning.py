"""Read-only Phase 5 Batch Match planning tests."""
from types import SimpleNamespace
from unittest.mock import Mock

from app.application.match_batch_planning import (
    BatchMatchPlanStatus,
    PlanBatchMatchUseCase,
)


def _readiness(job_id: str, *, ready: bool, blocker_codes: tuple[str, ...] = ()):
    return SimpleNamespace(
        job_id=job_id,
        inputs_release_eligible=ready,
        blockers=tuple(SimpleNamespace(code=code) for code in blocker_codes),
    )


def test_batch_match_plan_deduplicates_jobs_and_separates_ready_from_input_blocked() -> None:
    gate = Mock()
    gate.execute.side_effect = lambda job_id: {
        "job_ready": _readiness("job_ready", ready=True),
        "job_blocked": _readiness(
            "job_blocked",
            ready=False,
            blocker_codes=("requirement_human_review_pending",),
        ),
    }[job_id]

    result = PlanBatchMatchUseCase(
        readiness_gate=gate,
        persistence_ready=lambda: True,
    ).execute(("job_ready", "job_blocked", "job_ready"))

    assert result.total == 2
    assert result.ready_count == 1
    assert result.input_blocked_count == 1
    assert result.persistence_blocked_count == 0
    assert tuple(item.job_id for item in result.items) == ("job_ready", "job_blocked")
    assert result.items[0].status is BatchMatchPlanStatus.READY
    assert result.items[0].blocker_codes == ()
    assert result.items[1].status is BatchMatchPlanStatus.INPUT_BLOCKED
    assert result.items[1].blocker_codes == ("requirement_human_review_pending",)
    assert gate.execute.call_count == 2
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0


def test_batch_match_plan_marks_input_ready_jobs_persistence_blocked_without_execution() -> None:
    gate = Mock()
    gate.execute.side_effect = lambda job_id: _readiness(job_id, ready=True)

    result = PlanBatchMatchUseCase(
        readiness_gate=gate,
        persistence_ready=lambda: False,
    ).execute(("job_a", "job_b"))

    assert result.ready_count == 0
    assert result.input_blocked_count == 0
    assert result.persistence_blocked_count == 2
    assert all(
        item.status is BatchMatchPlanStatus.PERSISTENCE_BLOCKED
        for item in result.items
    )
    assert all(item.blocker_codes == ("match_report_persistence_not_ready",) for item in result.items)


def test_batch_match_plan_preserves_input_blockers_even_when_persistence_is_not_ready() -> None:
    gate = Mock()
    gate.execute.return_value = _readiness(
        "job_blocked",
        ready=False,
        blocker_codes=("career_context_not_ready", "requirement_not_ready"),
    )

    result = PlanBatchMatchUseCase(
        readiness_gate=gate,
        persistence_ready=lambda: False,
    ).execute(("job_blocked",))

    item = result.items[0]
    assert item.status is BatchMatchPlanStatus.INPUT_BLOCKED
    assert item.blocker_codes == ("career_context_not_ready", "requirement_not_ready")


def test_batch_match_plan_empty_input_is_zero_work() -> None:
    gate = Mock()
    persistence_ready = Mock(return_value=True)

    result = PlanBatchMatchUseCase(
        readiness_gate=gate,
        persistence_ready=persistence_ready,
    ).execute(())

    assert result.total == 0
    assert result.items == ()
    gate.execute.assert_not_called()
    persistence_ready.assert_not_called()
