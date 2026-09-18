"""Frozen LG-3 trajectory cohort for the durable Career Agent release gate.

Each case is materialized through the same SQLite checkpoint history used by the
runtime, then read back through ``build_persisted_trajectory_snapshot``.  The
cohort deliberately covers terminal and non-terminal control paths rather than
repeating one happy-path snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.evals.career_agent_runtime import (
    CareerAgentTrajectoryCase,
    build_persisted_trajectory_snapshot,
)


_FORBIDDEN_NODES = ("provider", "requirement_extraction", "semantic_match", "business_write")


@dataclass(frozen=True, slots=True)
class _Scenario:
    case_id: str
    steps: tuple[tuple[CareerAgentStatus, str], ...]
    human_decision: str | None = None
    error_class: str | None = None
    confirmed_job_ids: tuple[str, ...] = ()


def _scenarios() -> tuple[_Scenario, ...]:
    interrupt = ((CareerAgentStatus.RUNNING, "rank_jobs"), (CareerAgentStatus.INTERRUPTED, "target_cohort_confirmation"))
    approve = interrupt + (
        (CareerAgentStatus.RESUMING, "target_cohort_resume"),
        (CareerAgentStatus.RESUMING, "skill_gap_ready"),
        (CareerAgentStatus.COMPLETED, "skill_gap_completed"),
    )
    reject = interrupt + ((CareerAgentStatus.CANCELLED, "target_cohort_rejected"),)
    stale_profile = interrupt + (
        (CareerAgentStatus.RESUMING, "target_cohort_resume"),
        (CareerAgentStatus.STALE, "resume_stale_profile"),
    )
    stale_intent = interrupt + (
        (CareerAgentStatus.RESUMING, "target_cohort_resume"),
        (CareerAgentStatus.STALE, "resume_stale_search_intent"),
    )
    stale_match = interrupt + (
        (CareerAgentStatus.RESUMING, "target_cohort_resume"),
        (CareerAgentStatus.STALE, "resume_stale_match_reports"),
    )
    blocked_match = ((CareerAgentStatus.RUNNING, "rank_jobs"), (CareerAgentStatus.BLOCKED, "match_not_ready"))
    blocked_selection = interrupt + ((CareerAgentStatus.BLOCKED, "invalid_target_selection"),)
    return (
        _Scenario("approve_happy_path", approve, "approve", confirmed_job_ids=("job_1", "job_2")),
        _Scenario("approve_single_job", approve, "approve", confirmed_job_ids=("job_1",)),
        _Scenario("edit_single_job", approve, "edit", confirmed_job_ids=("job_2",)),
        _Scenario("edit_reordered_jobs", approve, "edit", confirmed_job_ids=("job_2", "job_1")),
        _Scenario("reject_target_cohort", reject, "reject"),
        _Scenario("stale_profile_version", stale_profile, "approve", "stale_profile"),
        _Scenario("stale_profile_identity", stale_profile, "edit", "stale_profile"),
        _Scenario("stale_search_intent_version", stale_intent, "approve", "stale_search_intent"),
        _Scenario("stale_search_intent_identity", stale_intent, "edit", "stale_search_intent"),
        _Scenario("stale_match_fingerprint", stale_match, "approve", "stale_match_reports"),
        _Scenario("stale_match_ordering", stale_match, "edit", "stale_match_reports"),
        _Scenario("missing_current_match", blocked_match, error_class="match_not_ready"),
        _Scenario("empty_ranking", blocked_match, error_class="match_not_ready"),
        _Scenario("invalid_target_selection", blocked_selection, error_class="invalid_target_selection"),
        _Scenario("restart_pending_interrupt", interrupt),
        _Scenario("duplicate_approve_replay", approve, "approve", confirmed_job_ids=("job_1", "job_2")),
        _Scenario("duplicate_edit_replay", approve, "edit", confirmed_job_ids=("job_2",)),
        _Scenario("restart_resume_completed", approve, "approve", confirmed_job_ids=("job_1", "job_2")),
        _Scenario("restart_edit_completed", approve, "edit", confirmed_job_ids=("job_2",)),
        _Scenario("duplicate_reject_replay", reject, "reject"),
    )


def _base_state(case_id: str) -> CareerAgentState:
    return CareerAgentState(
        thread_id=f"thread_{case_id}",
        run_id=f"run_{case_id}",
        request_id=f"request_{case_id}",
        status=CareerAgentStatus.CREATED,
        current_step="created",
        goal="analyze_target_cohort_gaps",
        profile_id="profile_1",
        profile_version=1,
        search_intent_id="intent_1",
        search_intent_version=1,
        requested_job_ids=("job_1", "job_2"),
        current_match_report_ids=("mr_1", "mr_2"),
        match_fingerprint="match_fingerprint_v1",
        ranked_job_ids=("job_1", "job_2"),
        proposed_target_job_ids=("job_1", "job_2"),
        provider_call_count=0,
    )


def build_frozen_runtime_trajectory_cases(*, database_path: str | Path) -> tuple[CareerAgentTrajectoryCase, ...]:
    """Materialize and reload the frozen 20-case LG-3 trajectory cohort."""

    store = SQLiteCareerAgentCheckpointStore(database_path)
    cases: list[CareerAgentTrajectoryCase] = []
    for scenario in _scenarios():
        state = _base_state(scenario.case_id)
        for index, (status, step) in enumerate(scenario.steps, start=1):
            state = replace(
                state,
                status=status,
                current_step=step,
                pending_approval=status is CareerAgentStatus.INTERRUPTED,
                interrupt_id=f"interrupt_{scenario.case_id}" if status is CareerAgentStatus.INTERRUPTED or state.interrupt_id else None,
                human_decision=scenario.human_decision if status not in (CareerAgentStatus.RUNNING, CareerAgentStatus.INTERRUPTED) else None,
                decision_action_id=(f"action_{scenario.case_id}" if scenario.human_decision and status not in (CareerAgentStatus.RUNNING, CareerAgentStatus.INTERRUPTED) else None),
                confirmed_target_job_ids=(scenario.confirmed_job_ids if status not in (CareerAgentStatus.RUNNING, CareerAgentStatus.INTERRUPTED) else ()),
                node_count=index,
                tool_call_count=1 + int(step in ("skill_gap_ready", "skill_gap_completed")),
                last_error_class=scenario.error_class if status in (CareerAgentStatus.STALE, CareerAgentStatus.BLOCKED) else None,
                gap_result_fingerprint=(f"gap_{scenario.case_id}" if status is CareerAgentStatus.COMPLETED else None),
            )
            store.save(state)

        snapshot = build_persisted_trajectory_snapshot(checkpoints=store, thread_id=state.thread_id)
        cases.append(
            CareerAgentTrajectoryCase(
                case_id=scenario.case_id,
                snapshot=snapshot,
                expected_status=scenario.steps[-1][0],
                expected_nodes=tuple(step for _, step in scenario.steps),
                forbidden_nodes=_FORBIDDEN_NODES,
                max_provider_calls=0,
                max_business_state_writes=0,
            )
        )
    return tuple(cases)


__all__ = ["build_frozen_runtime_trajectory_cases"]
