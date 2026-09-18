"""Executable trajectory harness for the LG-3 Career Agent release gate.

Unlike the frozen cohort materializer, this runner drives the real LangGraph,
HITL decision, stale guard, and Skill Gap resume handlers. The resulting eval
snapshot is always rebuilt from durable SQLite checkpoint history.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agent.context import CareerAgentContext
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.hitl_decision import HumanDecisionRequest, TargetCohortDecisionHandler
from app.agent.graph.langgraph_rank_interrupt import LangGraphRankToTargetCohortInterrupt
from app.agent.graph.resume_stale_guard import ResumeStaleGuard
from app.agent.graph.skill_gap_resume import SkillGapResumeExecutor
from app.agent.graph.state import CareerAgentStatus
from app.evals.career_agent_runtime import (
    CareerAgentTrajectoryCase,
    build_persisted_trajectory_snapshot,
)


_DEFAULT_FORBIDDEN_NODES = (
    "provider",
    "requirement_extraction",
    "semantic_match",
    "business_write",
)


@dataclass(frozen=True, slots=True)
class CareerAgentRuntimeTrajectoryRequest:
    case_id: str
    context: CareerAgentContext
    thread_id: str
    run_id: str
    request_id: str
    job_ids: tuple[str, ...]
    expected_status: CareerAgentStatus
    expected_nodes: tuple[str, ...]
    top_n: int = 5
    decision: HumanDecisionRequest | None = None
    replay_resume: bool = False


class CareerAgentRuntimeTrajectoryRunner:
    """Drive one real runtime path and return a persisted-trace eval case."""

    def __init__(
        self,
        *,
        checkpoints: SQLiteCareerAgentCheckpointStore,
        rank_interrupt: LangGraphRankToTargetCohortInterrupt,
        decisions: TargetCohortDecisionHandler,
        stale_guard: ResumeStaleGuard,
        gap_resume: SkillGapResumeExecutor,
    ) -> None:
        self._checkpoints = checkpoints
        self._rank_interrupt = rank_interrupt
        self._decisions = decisions
        self._stale_guard = stale_guard
        self._gap_resume = gap_resume

    def run(self, request: CareerAgentRuntimeTrajectoryRequest) -> CareerAgentTrajectoryCase:
        state = self._rank_interrupt.run(
            context=request.context,
            thread_id=request.thread_id,
            run_id=request.run_id,
            request_id=request.request_id,
            job_ids=request.job_ids,
            top_n=request.top_n,
        )

        if state.status is CareerAgentStatus.INTERRUPTED and request.decision is not None:
            state = self._decisions.submit(request.decision)
            if state.status is CareerAgentStatus.RESUMING:
                state = self._stale_guard.validate(thread_id=request.thread_id)
                if state.status is CareerAgentStatus.RESUMING and state.current_step == "skill_gap_ready":
                    state = self._gap_resume.execute(thread_id=request.thread_id)
                    if request.replay_resume:
                        replay = self._gap_resume.execute(thread_id=request.thread_id)
                        if replay != state:
                            raise AssertionError("duplicate resume changed the persisted runtime result")

        snapshot = build_persisted_trajectory_snapshot(
            checkpoints=self._checkpoints,
            thread_id=request.thread_id,
        )
        return CareerAgentTrajectoryCase(
            case_id=request.case_id,
            snapshot=snapshot,
            expected_status=request.expected_status,
            expected_nodes=request.expected_nodes,
            forbidden_nodes=_DEFAULT_FORBIDDEN_NODES,
            max_provider_calls=0,
            max_business_state_writes=0,
        )


__all__ = [
    "CareerAgentRuntimeTrajectoryRequest",
    "CareerAgentRuntimeTrajectoryRunner",
]
