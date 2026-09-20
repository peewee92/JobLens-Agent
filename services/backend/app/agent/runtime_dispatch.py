"""Runtime dispatch boundary for Career Agent vNext 1.1.

The dispatcher chooses between the bounded governed tool loop and the existing
vNext 1.0 durable HITL runtime. It does not interpret natural language itself;
it accepts an already-structured CareerIntent and revalidates its grounded job
scope before dispatching.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.agent.context import CareerAgentContext
from app.agent.governed_loop_runtime import (
    CareerAgentGovernedLoopResult,
    CareerAgentPlannedToolRequest,
)
from app.agent.graph.hitl_service import StartCareerAgentRunRequest
from app.agent.graph.state import CareerAgentState
from app.agent.intent import (
    CareerIntent,
    CareerIntentGoal,
    CareerIntentResolutionContext,
    CareerIntentResolver,
)


class CareerAgentRuntimeDispatchError(ValueError):
    """Raised before execution when a runtime route lacks required governed facts."""


class CareerAgentRuntimeDispatchKind(StrEnum):
    GOVERNED_LOOP = "governed_loop"
    DURABLE_HITL = "durable_hitl"


@dataclass(frozen=True, slots=True)
class CareerAgentDurableRunIdentity:
    thread_id: str
    run_id: str
    request_id: str
    top_n: int = 5

    def __post_init__(self) -> None:
        if not self.thread_id or not self.run_id or not self.request_id:
            raise ValueError("durable run identity requires thread_id, run_id, and request_id")
        if self.top_n <= 0:
            raise ValueError("durable run top_n must be positive")


@dataclass(frozen=True, slots=True)
class CareerAgentRuntimeDispatchRequest:
    user_message: str
    intent: CareerIntent
    context: CareerAgentContext
    resolution_context: CareerIntentResolutionContext
    planned_requests: tuple[CareerAgentPlannedToolRequest, ...] = ()
    durable_run: CareerAgentDurableRunIdentity | None = None

    def __post_init__(self) -> None:
        if not self.user_message.strip():
            raise ValueError("runtime dispatch requires a user message")


@dataclass(frozen=True, slots=True)
class CareerAgentRuntimeDispatchResult:
    kind: CareerAgentRuntimeDispatchKind
    loop_result: CareerAgentGovernedLoopResult | None = None
    durable_state: CareerAgentState | None = None

    def __post_init__(self) -> None:
        if self.kind is CareerAgentRuntimeDispatchKind.GOVERNED_LOOP:
            if self.loop_result is None or self.durable_state is not None:
                raise ValueError("governed loop dispatch requires only loop_result")
        elif self.kind is CareerAgentRuntimeDispatchKind.DURABLE_HITL:
            if self.durable_state is None or self.loop_result is not None:
                raise ValueError("durable HITL dispatch requires only durable_state")


class CareerAgentResolvedIntentRuntime(Protocol):
    def run(
        self,
        *,
        user_message: str,
        context: CareerAgentContext,
        resolution_context: CareerIntentResolutionContext,
        planned_requests: tuple[CareerAgentPlannedToolRequest, ...],
        resolved_intent: CareerIntent | None = None,
    ) -> CareerAgentGovernedLoopResult: ...


class CareerAgentDurableHitlStarter(Protocol):
    def start(self, request: StartCareerAgentRunRequest) -> CareerAgentState: ...


class CareerAgentRuntimeDispatcher:
    """Dispatch compound rank→gap intent to durable HITL; keep simple turns bounded."""

    _DURABLE_HITL_GOALS = (
        CareerIntentGoal.RANK_JOBS,
        CareerIntentGoal.REVIEW_GAPS,
    )

    def __init__(
        self,
        *,
        governed_runtime: CareerAgentResolvedIntentRuntime,
        hitl_service: CareerAgentDurableHitlStarter,
    ) -> None:
        self._governed_runtime = governed_runtime
        self._hitl_service = hitl_service
        self._resolver = CareerIntentResolver()

    def run(
        self,
        request: CareerAgentRuntimeDispatchRequest,
    ) -> CareerAgentRuntimeDispatchResult:
        intent = self._resolver.resolve(
            intent=request.intent,
            context=request.resolution_context,
        )

        if intent.goals == self._DURABLE_HITL_GOALS:
            durable = request.durable_run
            if durable is None:
                raise CareerAgentRuntimeDispatchError(
                    "rank_jobs → review_gaps requires explicit durable run identity"
                )
            job_ids = intent.referenced_job_ids or request.resolution_context.run_job_ids
            if not job_ids:
                raise CareerAgentRuntimeDispatchError(
                    "rank_jobs → review_gaps requires governed job scope"
                )
            state = self._hitl_service.start(
                StartCareerAgentRunRequest(
                    thread_id=durable.thread_id,
                    run_id=durable.run_id,
                    request_id=durable.request_id,
                    job_ids=job_ids,
                    top_n=durable.top_n,
                )
            )
            return CareerAgentRuntimeDispatchResult(
                kind=CareerAgentRuntimeDispatchKind.DURABLE_HITL,
                durable_state=state,
            )

        loop_result = self._governed_runtime.run(
            user_message=request.user_message,
            context=request.context,
            resolution_context=request.resolution_context,
            planned_requests=request.planned_requests,
            resolved_intent=intent,
        )
        return CareerAgentRuntimeDispatchResult(
            kind=CareerAgentRuntimeDispatchKind.GOVERNED_LOOP,
            loop_result=loop_result,
        )


__all__ = [
    "CareerAgentDurableRunIdentity",
    "CareerAgentRuntimeDispatchError",
    "CareerAgentRuntimeDispatchKind",
    "CareerAgentRuntimeDispatchRequest",
    "CareerAgentRuntimeDispatchResult",
    "CareerAgentRuntimeDispatcher",
]
