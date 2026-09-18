from __future__ import annotations

from dataclasses import replace

import pytest

from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.evals.career_agent_runtime import (
    CareerAgentTrajectoryCase,
    CareerAgentTrajectorySnapshot,
    build_persisted_trajectory_snapshot,
    evaluate_career_agent_trajectories,
)


def _state(**overrides) -> CareerAgentState:
    base = CareerAgentState(
        thread_id="thread_eval",
        run_id="run_eval",
        request_id="request_eval",
        status=CareerAgentStatus.COMPLETED,
        current_step="skill_gap_completed",
        goal="analyze_target_cohort_gaps",
        requested_job_ids=("job_1", "job_2"),
        current_match_report_ids=("mr_1", "mr_2"),
        match_fingerprint="fingerprint",
        ranked_job_ids=("job_1", "job_2"),
        proposed_target_job_ids=("job_1", "job_2"),
        confirmed_target_job_ids=("job_1", "job_2"),
        human_decision="approve",
        decision_action_id="action_1",
        node_count=4,
        tool_call_count=2,
        provider_call_count=0,
        gap_result_fingerprint="gap_fingerprint",
    )
    return replace(base, **overrides)


def test_persisted_checkpoint_trace_builds_runtime_snapshot_without_duplicate_events(tmp_path) -> None:
    store = SQLiteCareerAgentCheckpointStore(tmp_path / "runtime.sqlite3")
    interrupted = _state(
        status=CareerAgentStatus.INTERRUPTED,
        current_step="target_cohort_confirmation",
        pending_approval=True,
        human_decision=None,
        decision_action_id=None,
        confirmed_target_job_ids=(),
        gap_result_fingerprint=None,
        node_count=2,
        tool_call_count=1,
    )
    resuming = replace(
        interrupted,
        status=CareerAgentStatus.RESUMING,
        current_step="target_cohort_resume",
        pending_approval=False,
        human_decision="approve",
        decision_action_id="action_trace",
        confirmed_target_job_ids=("job_1", "job_2"),
    )
    ready = replace(resuming, current_step="skill_gap_ready", node_count=3, tool_call_count=2)
    completed = replace(
        ready,
        status=CareerAgentStatus.COMPLETED,
        current_step="skill_gap_completed",
        node_count=4,
        gap_result_fingerprint="gap_trace",
    )

    store.save(interrupted)
    store.save(interrupted)
    store.save(resuming)
    store.save(ready)
    store.save(completed)

    snapshot = build_persisted_trajectory_snapshot(checkpoints=store, thread_id="thread_eval")

    assert snapshot.state == completed
    assert snapshot.visited_nodes == (
        "target_cohort_confirmation",
        "target_cohort_resume",
        "skill_gap_ready",
        "skill_gap_completed",
    )
    assert snapshot.business_state_writes == 0


def test_trajectory_eval_requires_twenty_cases() -> None:
    case = CareerAgentTrajectoryCase(
        case_id="only_one",
        snapshot=CareerAgentTrajectorySnapshot(
            state=_state(),
            visited_nodes=("rank_jobs", "persist_interrupt", "resume", "skill_gap"),
            business_state_writes=0,
        ),
        expected_status=CareerAgentStatus.COMPLETED,
        expected_nodes=("rank_jobs", "persist_interrupt", "resume", "skill_gap"),
    )

    with pytest.raises(ValueError, match="at least 20"):
        evaluate_career_agent_trajectories(cases=(case,))


def test_twenty_case_release_gate_passes_and_reports_guardrail_failures() -> None:
    happy = CareerAgentTrajectorySnapshot(
        state=_state(),
        visited_nodes=("rank_jobs", "persist_interrupt", "resume", "skill_gap"),
        business_state_writes=0,
    )
    cases = tuple(
        CareerAgentTrajectoryCase(
            case_id=f"case_{index:02d}",
            snapshot=happy,
            expected_status=CareerAgentStatus.COMPLETED,
            expected_nodes=("rank_jobs", "persist_interrupt", "resume", "skill_gap"),
            forbidden_nodes=("provider", "requirement_extraction", "semantic_match"),
            max_provider_calls=0,
            max_business_state_writes=0,
        )
        for index in range(20)
    )

    report = evaluate_career_agent_trajectories(cases=cases)

    assert report.total_cases == 20
    assert report.passed_cases == 20
    assert report.gate_passed is True

    unsafe = replace(
        cases[-1],
        snapshot=CareerAgentTrajectorySnapshot(
            state=_state(provider_call_count=1),
            visited_nodes=("rank_jobs", "provider", "persist_interrupt", "resume", "skill_gap"),
            business_state_writes=1,
        ),
    )
    failed = evaluate_career_agent_trajectories(cases=cases[:-1] + (unsafe,))

    assert failed.gate_passed is False
    assert failed.failed_cases == 1
    reasons = failed.case_results[-1].failure_reasons
    assert any("forbidden node" in reason for reason in reasons)
    assert any("provider call" in reason for reason in reasons)
    assert any("business state write" in reason for reason in reasons)
