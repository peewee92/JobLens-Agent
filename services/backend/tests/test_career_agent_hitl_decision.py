from __future__ import annotations

import pytest

from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.hitl_decision import (
    HumanDecisionConflictError,
    HumanDecisionRequest,
    HumanDecisionValidationError,
    TargetCohortDecisionHandler,
)
from app.agent.graph.state import CareerAgentState, CareerAgentStatus


def _interrupted_state() -> CareerAgentState:
    return CareerAgentState(
        thread_id="thread_1",
        run_id="run_1",
        request_id="request_1",
        status=CareerAgentStatus.INTERRUPTED,
        current_step="target_cohort_confirmation",
        goal="analyze_target_cohort_gaps",
        profile_id="profile_1",
        profile_version=3,
        search_intent_id="intent_1",
        search_intent_version=2,
        requested_job_ids=("job_1", "job_2", "job_3"),
        current_match_report_ids=("mr_1", "mr_2", "mr_3"),
        match_fingerprint="fingerprint_1",
        ranked_job_ids=("job_1", "job_2", "job_3"),
        proposed_target_job_ids=("job_1", "job_2"),
        pending_approval=True,
        interrupt_id="interrupt_1",
        node_count=2,
        tool_call_count=1,
    )


def _handler(tmp_path):
    store = SQLiteCareerAgentCheckpointStore(tmp_path / "agent.sqlite3")
    store.save(_interrupted_state())
    return TargetCohortDecisionHandler(checkpoints=store), store


def test_approve_consumes_interrupt_once_and_persists_resuming_state(tmp_path) -> None:
    handler, store = _handler(tmp_path)
    request = HumanDecisionRequest(
        thread_id="thread_1",
        interrupt_id="interrupt_1",
        action_id="action_1",
        decision="approve",
    )

    result = handler.submit(request)

    assert result.status is CareerAgentStatus.RESUMING
    assert result.current_step == "target_cohort_resume"
    assert result.confirmed_target_job_ids == ("job_1", "job_2")
    assert result.pending_approval is False
    assert result.human_decision == "approve"
    assert result.decision_action_id == "action_1"
    assert store.load(thread_id="thread_1") == result

    replay = handler.submit(request)
    assert replay == result


def test_edit_requires_bounded_selection_inside_original_run_scope(tmp_path) -> None:
    handler, _ = _handler(tmp_path)

    result = handler.submit(
        HumanDecisionRequest(
            thread_id="thread_1",
            interrupt_id="interrupt_1",
            action_id="action_edit",
            decision="edit",
            selected_job_ids=("job_3", "job_1", "job_3"),
        )
    )
    assert result.confirmed_target_job_ids == ("job_3", "job_1")
    assert result.human_decision == "edit"

    handler, _ = _handler(tmp_path / "empty")
    with pytest.raises(HumanDecisionValidationError):
        handler.submit(
            HumanDecisionRequest(
                thread_id="thread_1",
                interrupt_id="interrupt_1",
                action_id="empty_edit",
                decision="edit",
                selected_job_ids=(),
            )
        )

    handler, _ = _handler(tmp_path / "outside")
    with pytest.raises(HumanDecisionValidationError):
        handler.submit(
            HumanDecisionRequest(
                thread_id="thread_1",
                interrupt_id="interrupt_1",
                action_id="outside_edit",
                decision="edit",
                selected_job_ids=("job_outside",),
            )
        )


def test_reject_cancels_without_downstream_work_and_conflicting_replay_is_rejected(tmp_path) -> None:
    handler, store = _handler(tmp_path)
    rejected = handler.submit(
        HumanDecisionRequest(
            thread_id="thread_1",
            interrupt_id="interrupt_1",
            action_id="reject_1",
            decision="reject",
        )
    )

    assert rejected.status is CareerAgentStatus.CANCELLED
    assert rejected.current_step == "target_cohort_rejected"
    assert rejected.confirmed_target_job_ids == ()
    assert rejected.tool_call_count == 1
    assert rejected.provider_call_count == 0
    assert store.load(thread_id="thread_1") == rejected

    with pytest.raises(HumanDecisionConflictError):
        handler.submit(
            HumanDecisionRequest(
                thread_id="thread_1",
                interrupt_id="interrupt_1",
                action_id="approve_after_reject",
                decision="approve",
            )
        )


def test_wrong_interrupt_id_fails_without_mutating_checkpoint(tmp_path) -> None:
    handler, store = _handler(tmp_path)
    before = store.load(thread_id="thread_1")

    with pytest.raises(HumanDecisionValidationError):
        handler.submit(
            HumanDecisionRequest(
                thread_id="thread_1",
                interrupt_id="wrong_interrupt",
                action_id="action_wrong",
                decision="approve",
            )
        )

    assert store.load(thread_id="thread_1") == before
