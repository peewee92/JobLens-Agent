"""Deterministic release gate for durable Career Agent trajectories.

LG-3 evaluates runtime control behavior rather than final prose. The snapshot is
intentionally compact: explicit runtime state, visited node names, and the
number of business-state writes observed by the harness. Provider calls come
from the runtime state's own bounded counter.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.state import CareerAgentState, CareerAgentStatus


MIN_RELEASE_GATE_CASES = 20


@dataclass(frozen=True, slots=True)
class CareerAgentTrajectorySnapshot:
    state: CareerAgentState
    visited_nodes: tuple[str, ...]
    business_state_writes: int = 0


@dataclass(frozen=True, slots=True)
class CareerAgentTrajectoryCase:
    case_id: str
    snapshot: CareerAgentTrajectorySnapshot
    expected_status: CareerAgentStatus
    expected_nodes: tuple[str, ...] = ()
    forbidden_nodes: tuple[str, ...] = ()
    max_provider_calls: int = 0
    max_business_state_writes: int = 0


@dataclass(frozen=True, slots=True)
class CareerAgentTrajectoryCaseResult:
    case_id: str
    passed: bool
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CareerAgentTrajectoryEvalReport:
    total_cases: int
    passed_cases: int
    failed_cases: int
    gate_passed: bool
    case_results: tuple[CareerAgentTrajectoryCaseResult, ...]


def build_persisted_trajectory_snapshot(
    *, checkpoints: SQLiteCareerAgentCheckpointStore, thread_id: str
) -> CareerAgentTrajectorySnapshot:
    """Build a compact trace from durable state transitions, not process memory."""

    history = checkpoints.load_history(thread_id=thread_id)
    if not history:
        raise ValueError(f"no persisted Career Agent trajectory for thread {thread_id!r}")
    return CareerAgentTrajectorySnapshot(
        state=history[-1],
        visited_nodes=tuple(state.current_step for state in history),
        business_state_writes=0,
    )


def evaluate_career_agent_trajectories(
    *, cases: tuple[CareerAgentTrajectoryCase, ...]
) -> CareerAgentTrajectoryEvalReport:
    """Grade a frozen trajectory cohort with an all-cases release gate."""

    if len(cases) < MIN_RELEASE_GATE_CASES:
        raise ValueError(
            f"Career Agent runtime release gate requires at least {MIN_RELEASE_GATE_CASES} cases"
        )
    case_ids = tuple(case.case_id for case in cases)
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Career Agent runtime release gate requires unique case IDs")

    results = tuple(_evaluate_case(case) for case in cases)
    passed_cases = sum(result.passed for result in results)
    return CareerAgentTrajectoryEvalReport(
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=len(results) - passed_cases,
        gate_passed=passed_cases == len(results),
        case_results=results,
    )


def _evaluate_case(case: CareerAgentTrajectoryCase) -> CareerAgentTrajectoryCaseResult:
    snapshot = case.snapshot
    failures: list[str] = []

    if snapshot.state.status is not case.expected_status:
        failures.append(
            f"expected status {case.expected_status.value!r}, got {snapshot.state.status.value!r}"
        )

    visited = snapshot.visited_nodes
    cursor = 0
    for expected in case.expected_nodes:
        try:
            cursor = visited.index(expected, cursor) + 1
        except ValueError:
            failures.append(f"expected node {expected!r} was not visited in order")
            break

    forbidden_visited = tuple(node for node in case.forbidden_nodes if node in visited)
    if forbidden_visited:
        failures.append("forbidden node visited: " + ", ".join(forbidden_visited))

    if snapshot.state.provider_call_count > case.max_provider_calls:
        failures.append(
            "provider call budget exceeded: "
            f"{snapshot.state.provider_call_count} > {case.max_provider_calls}"
        )
    if snapshot.business_state_writes > case.max_business_state_writes:
        failures.append(
            "business state write budget exceeded: "
            f"{snapshot.business_state_writes} > {case.max_business_state_writes}"
        )

    return CareerAgentTrajectoryCaseResult(
        case_id=case.case_id,
        passed=not failures,
        failure_reasons=tuple(failures),
    )


__all__ = [
    "CareerAgentTrajectoryCase",
    "CareerAgentTrajectoryCaseResult",
    "CareerAgentTrajectoryEvalReport",
    "CareerAgentTrajectorySnapshot",
    "MIN_RELEASE_GATE_CASES",
    "build_persisted_trajectory_snapshot",
    "evaluate_career_agent_trajectories",
]
