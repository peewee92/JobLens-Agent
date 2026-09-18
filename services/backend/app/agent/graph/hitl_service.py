"""Application-facing seam for the first durable Career Agent HITL flow."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.agent.context import CareerAgentContextBuilder
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.hitl_decision import HumanDecisionRequest, TargetCohortDecisionHandler
from app.agent.graph.langgraph_rank_interrupt import LangGraphRankToTargetCohortInterrupt
from app.agent.graph.resume_stale_guard import ResumeStaleGuard
from app.agent.graph.skill_gap_resume import SkillGapResumeExecutor
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.agent.tool_registry import CareerAgentToolRegistry


@dataclass(frozen=True, slots=True)
class StartCareerAgentRunRequest:
    thread_id: str
    run_id: str
    request_id: str
    job_ids: tuple[str, ...]
    top_n: int = 5


@dataclass(frozen=True, slots=True)
class ResumeCareerAgentRunRequest:
    thread_id: str
    interrupt_id: str
    action_id: str
    decision: Literal["approve", "edit", "reject"]
    selected_job_ids: tuple[str, ...] = ()


class CareerAgentHitlService:
    """Expose Run/Get/Resume without leaking LangGraph types into the API layer."""

    def __init__(
        self,
        *,
        checkpoints: SQLiteCareerAgentCheckpointStore,
        context_builder: CareerAgentContextBuilder,
        tool_registry: CareerAgentToolRegistry,
    ) -> None:
        self._checkpoints = checkpoints
        self._context_builder = context_builder
        self._rank_interrupt = LangGraphRankToTargetCohortInterrupt(
            tool_registry=tool_registry,
            checkpoints=checkpoints,
        )
        self._decisions = TargetCohortDecisionHandler(checkpoints=checkpoints)
        self._stale_guard = ResumeStaleGuard(
            checkpoints=checkpoints,
            context_builder=context_builder,
            tool_registry=tool_registry,
        )
        self._gap_resume = SkillGapResumeExecutor(
            checkpoints=checkpoints,
            context_builder=context_builder,
            tool_registry=tool_registry,
        )

    def start(self, request: StartCareerAgentRunRequest) -> CareerAgentState:
        existing = self._checkpoints.load(thread_id=request.thread_id)
        if existing is not None:
            if existing.run_id == request.run_id and existing.request_id == request.request_id:
                return existing
            raise ValueError("career agent thread already exists")
        context = self._context_builder.build()
        return self._rank_interrupt.run(
            context=context,
            thread_id=request.thread_id,
            run_id=request.run_id,
            request_id=request.request_id,
            job_ids=request.job_ids,
            top_n=request.top_n,
        )

    def get_state(self, *, thread_id: str) -> CareerAgentState | None:
        return self._checkpoints.load(thread_id=thread_id)

    def resume(self, request: ResumeCareerAgentRunRequest) -> CareerAgentState:
        decided = self._decisions.submit(
            HumanDecisionRequest(
                thread_id=request.thread_id,
                interrupt_id=request.interrupt_id,
                action_id=request.action_id,
                decision=request.decision,
                selected_job_ids=request.selected_job_ids,
            )
        )
        if decided.status is CareerAgentStatus.CANCELLED:
            return decided
        validated = self._stale_guard.validate(thread_id=request.thread_id)
        if validated.status is not CareerAgentStatus.RESUMING:
            return validated
        return self._gap_resume.execute(thread_id=request.thread_id)


__all__ = [
    "CareerAgentHitlService",
    "ResumeCareerAgentRunRequest",
    "StartCareerAgentRunRequest",
]
