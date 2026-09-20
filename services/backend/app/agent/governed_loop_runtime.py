"""Minimal governed natural-language tool-loop runtime for Career Agent vNext 1.1.

This vertical seam composes the already-frozen intent, selection, execution-gate,
registry, structured-result, and loop-guard contracts.  It intentionally does
not add a second business workflow layer or a free-form model-driven executor.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.agent.context import CareerAgentContext
from app.agent.execution_gate import (
    CareerAgentExecutionGateOutcome,
    CareerAgentGovernedToolExecutor,
    CareerAgentPendingAction,
)
from app.agent.intent import (
    CareerIntent,
    CareerIntentGoal,
    CareerIntentResolutionContext,
    CareerIntentRouter,
)
from app.agent.tool_loop import (
    CareerAgentLoopBudget,
    CareerAgentLoopDecision,
    CareerAgentLoopError,
    CareerAgentLoopErrorCode,
    CareerAgentLoopGuard,
    CareerAgentLoopObservation,
)
from app.agent.tool_registry import CareerAgentToolName, CareerAgentToolRequest
from app.agent.tool_result import AgentToolResult, AgentToolResultStatus
from app.agent.tool_selection import CareerAgentToolSelectionError, CareerAgentToolSelector


class CareerAgentGovernedLoopStatus(StrEnum):
    COMPLETED = "completed"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"
    PENDING_ACTION = "pending_action"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CareerAgentPlannedToolRequest:
    """Caller-supplied, already-grounded arguments for one selected workflow."""

    tool: CareerAgentToolName
    request: CareerAgentToolRequest
    normalized_params: tuple[tuple[str, str], ...]
    fact_fingerprint: str
    expected_provider_calls: int = 0
    business_writes: int = 0
    external_effects: tuple[str, ...] = ()
    expires_at: str | None = None

    def __post_init__(self) -> None:
        if not _is_sha256_digest(self.fact_fingerprint):
            raise ValueError(
                "planned tool request fact_fingerprint must be a 64-character lowercase sha256 digest"
            )


class CareerAgentLoopRecoveryPlanner(Protocol):
    """Provide one corrected governed request after a retryable tool-level error."""

    def recover_tool_request(
        self,
        *,
        tool: CareerAgentToolName,
        error_code: str,
        previous_plan: CareerAgentPlannedToolRequest | None,
        attempt: int,
    ) -> CareerAgentPlannedToolRequest | None: ...


class CareerAgentUnknownToolReplanner(Protocol):
    """Replace only unknown goals without widening grounded references."""

    def replan_unknown_tool(
        self,
        *,
        previous_goals: tuple[CareerIntentGoal, ...],
        attempt: int,
    ) -> tuple[CareerIntentGoal, ...] | None: ...


class CareerAgentStalenessGuard(Protocol):
    """Revalidate the planned request against current governed facts before execution."""

    def is_stale(
        self,
        *,
        context: CareerAgentContext,
        plan: CareerAgentPlannedToolRequest,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class CareerAgentGovernedLoopTraceEvent:
    sequence: int
    event: str
    tool: CareerAgentToolName | None
    input_fingerprint: str
    result_fingerprint: str | None
    error_code: str | None
    trace_fingerprint: str


@dataclass(frozen=True, slots=True)
class CareerAgentGovernedLoopResult:
    status: CareerAgentGovernedLoopStatus
    tool_results: tuple[AgentToolResult, ...]
    trace: tuple[CareerAgentGovernedLoopTraceEvent, ...]
    message: str | None = None
    pending_action: CareerAgentPendingAction | None = None
    error_code: str | None = None


class CareerAgentGovernedLoopRuntime:
    """Compose vNext 1.1 governance boundaries into one bounded runnable path."""

    def __init__(
        self,
        *,
        router: CareerIntentRouter,
        selector: CareerAgentToolSelector,
        executor: CareerAgentGovernedToolExecutor,
        staleness_guard: CareerAgentStalenessGuard,
        budget: CareerAgentLoopBudget | None = None,
        recovery_planner: CareerAgentLoopRecoveryPlanner | None = None,
        unknown_tool_replanner: CareerAgentUnknownToolReplanner | None = None,
    ) -> None:
        self._router = router
        self._selector = selector
        self._executor = executor
        self._staleness_guard = staleness_guard
        self._budget = budget or CareerAgentLoopBudget()
        self._recovery_planner = recovery_planner
        self._unknown_tool_replanner = unknown_tool_replanner

    def run(
        self,
        *,
        user_message: str,
        context: CareerAgentContext,
        resolution_context: CareerIntentResolutionContext,
        planned_requests: tuple[CareerAgentPlannedToolRequest, ...],
    ) -> CareerAgentGovernedLoopResult:
        guard = CareerAgentLoopGuard(self._budget)
        trace: list[CareerAgentGovernedLoopTraceEvent] = []
        results: list[AgentToolResult] = []
        input_fingerprint = _fingerprint(
            {
                "message": user_message,
                "current_job_id": resolution_context.current_job_id,
                "run_job_ids": resolution_context.run_job_ids,
            }
        )

        try:
            intent = self._router.route(user_message=user_message, context=resolution_context)
        except ValueError:
            error = guard.record_error(
                CareerAgentLoopError(
                    code=CareerAgentLoopErrorCode.INVALID_INTENT_OUTPUT,
                    message="Career Agent intent output is invalid",
                    retryable=True,
                )
            )
            return self._failed(trace, results, input_fingerprint, error)
        self._trace(trace, "intent_routed", input_fingerprint=input_fingerprint)
        if intent.needs_clarification:
            self._trace(trace, "clarification", input_fingerprint=input_fingerprint)
            return CareerAgentGovernedLoopResult(
                status=CareerAgentGovernedLoopStatus.CLARIFICATION_REQUIRED,
                tool_results=(),
                trace=tuple(trace),
                message=intent.clarification_question,
            )
        if intent.unsupported_request:
            self._trace(trace, "unsupported", input_fingerprint=input_fingerprint)
            return CareerAgentGovernedLoopResult(
                status=CareerAgentGovernedLoopStatus.UNSUPPORTED,
                tool_results=(),
                trace=tuple(trace),
                message=intent.unsupported_request,
            )
        if not context.usable:
            self._trace(trace, "blocked", input_fingerprint=input_fingerprint)
            return CareerAgentGovernedLoopResult(
                status=CareerAgentGovernedLoopStatus.BLOCKED,
                tool_results=(),
                trace=tuple(trace),
                message="Career Agent context is not usable.",
            )

        unknown_replan_attempt = 0
        while True:
            try:
                selections = self._selector.select(intent)
                break
            except CareerAgentToolSelectionError:
                if CareerIntentGoal.UNKNOWN not in intent.goals:
                    error = guard.record_error(
                        CareerAgentLoopError(
                            code=CareerAgentLoopErrorCode.INVALID_TOOL_PARAMS,
                            message="Career Agent tool selection is invalid",
                            retryable=True,
                        )
                    )
                    return self._failed(trace, results, input_fingerprint, error)

                error = guard.record_error(
                    CareerAgentLoopError.unknown_tool(CareerIntentGoal.UNKNOWN.value)
                )
                if not error.retryable or self._unknown_tool_replanner is None:
                    return self._failed(trace, results, input_fingerprint, error)
                unknown_replan_attempt += 1
                replanned_goals = self._unknown_tool_replanner.replan_unknown_tool(
                    previous_goals=intent.goals,
                    attempt=unknown_replan_attempt,
                )
                if not replanned_goals:
                    return self._failed(
                        trace,
                        results,
                        input_fingerprint,
                        CareerAgentLoopError(
                            code=CareerAgentLoopErrorCode.UNKNOWN_TOOL,
                            message="Career Agent unknown tool could not be replanned",
                            retryable=False,
                        ),
                    )
                self._trace(
                    trace,
                    "recovery",
                    input_fingerprint=input_fingerprint,
                    error_code=error.code.value,
                )
                intent = _replace_intent_goals(intent, replanned_goals)
            except ValueError:
                error = guard.record_error(
                    CareerAgentLoopError(
                        code=CareerAgentLoopErrorCode.INVALID_TOOL_PARAMS,
                        message="Career Agent tool selection is invalid",
                        retryable=True,
                    )
                )
                return self._failed(trace, results, input_fingerprint, error)

        if not selections:
            self._trace(trace, "clarification", input_fingerprint=input_fingerprint)
            return CareerAgentGovernedLoopResult(
                status=CareerAgentGovernedLoopStatus.CLARIFICATION_REQUIRED,
                tool_results=(),
                trace=tuple(trace),
                message="No executable Career Agent tool was selected. Please clarify the next action.",
            )

        try:
            plans = _index_plans(planned_requests)
        except ValueError:
            error = guard.record_error(
                CareerAgentLoopError(
                    code=CareerAgentLoopErrorCode.INVALID_TOOL_PARAMS,
                    message="Career Agent tool plan is invalid",
                    retryable=True,
                )
            )
            return self._failed(trace, results, input_fingerprint, error)

        for selection in selections:
            self._trace(
                trace,
                "tool_selected",
                tool=selection.tool.name,
                input_fingerprint=input_fingerprint,
            )
            plan = plans.get(selection.tool.name)
            if plan is None:
                error = guard.record_error(
                    CareerAgentLoopError.invalid_tool_params(selection.tool.name)
                )
                return self._failed(trace, results, input_fingerprint, error)

            recovery_attempt = 0
            transient_retry = False
            while True:
                if self._staleness_guard.is_stale(context=context, plan=plan):
                    return self._failed(
                        trace,
                        results,
                        plan.fact_fingerprint,
                        CareerAgentLoopError.stale_state(selection.tool.name),
                        tool=selection.tool.name,
                    )
                try:
                    guard.record_turn()
                except CareerAgentLoopError as error:
                    return self._failed(
                        trace,
                        results,
                        plan.fact_fingerprint,
                        guard.record_error(error),
                        tool=selection.tool.name,
                    )

                arguments_fingerprint = _fingerprint(plan.normalized_params)
                decision = CareerAgentLoopDecision.call_tool(
                    tool=selection.tool.name,
                    arguments_fingerprint=arguments_fingerprint,
                )
                try:
                    guard.record_tool_call(
                        decision,
                        input_fingerprint=plan.fact_fingerprint,
                        transient_retry=transient_retry,
                    )
                    execution = self._executor.execute(
                        context=context,
                        tool=plan.tool,
                        request=plan.request,
                        normalized_params=plan.normalized_params,
                        fact_fingerprint=plan.fact_fingerprint,
                        expected_provider_calls=plan.expected_provider_calls,
                        business_writes=plan.business_writes,
                        external_effects=plan.external_effects,
                        expires_at=plan.expires_at,
                    )
                    break
                except (ConnectionError, TimeoutError):
                    error = guard.record_error(CareerAgentLoopError.transient_network(selection.tool.name))
                    if not error.retryable:
                        return self._failed(trace, results, plan.fact_fingerprint, error, tool=selection.tool.name)
                    recovery_attempt += 1
                    self._trace(
                        trace,
                        "recovery",
                        tool=selection.tool.name,
                        input_fingerprint=plan.fact_fingerprint,
                        error_code=error.code.value,
                    )
                    transient_retry = True
                except CareerAgentLoopError as error:
                    return self._failed(
                        trace,
                        results,
                        plan.fact_fingerprint,
                        guard.record_error(error),
                        tool=selection.tool.name,
                    )
                except ValueError:
                    error = guard.record_error(CareerAgentLoopError.invalid_tool_params(selection.tool.name))
                    if not error.retryable or self._recovery_planner is None:
                        return self._failed(trace, results, plan.fact_fingerprint, error, tool=selection.tool.name)
                    recovery_attempt += 1
                    recovered_plan = self._recovery_planner.recover_tool_request(
                        tool=selection.tool.name,
                        error_code=error.code.value,
                        previous_plan=plan,
                        attempt=recovery_attempt,
                    )
                    if recovered_plan is None or recovered_plan.tool is not selection.tool.name:
                        return self._failed(
                            trace,
                            results,
                            plan.fact_fingerprint,
                            CareerAgentLoopError(code=error.code, message=str(error), retryable=False),
                            tool=selection.tool.name,
                        )
                    self._trace(
                        trace,
                        "recovery",
                        tool=selection.tool.name,
                        input_fingerprint=recovered_plan.fact_fingerprint,
                        error_code=error.code.value,
                    )
                    plan = recovered_plan
                    transient_retry = False

            self._trace(
                trace,
                "tool_called",
                tool=plan.tool,
                input_fingerprint=plan.fact_fingerprint,
            )
            if execution.gate.outcome is CareerAgentExecutionGateOutcome.PENDING_ACTION:
                self._trace(
                    trace,
                    "pending_action",
                    tool=plan.tool,
                    input_fingerprint=plan.fact_fingerprint,
                )
                return CareerAgentGovernedLoopResult(
                    status=CareerAgentGovernedLoopStatus.PENDING_ACTION,
                    tool_results=tuple(results),
                    trace=tuple(trace),
                    pending_action=execution.gate.pending_action,
                )

            tool_result = _structured_success_result(
                tool=plan.tool,
                output=execution.output,
            )
            results.append(tool_result)
            try:
                guard.record_observation(
                    CareerAgentLoopObservation(
                        state_fingerprint=tool_result.result_fingerprint,
                        blocker_fingerprint=_fingerprint(tool_result.blockers),
                        fact_fingerprint=plan.fact_fingerprint,
                    )
                )
            except CareerAgentLoopError as error:
                return self._failed(
                    trace,
                    results,
                    plan.fact_fingerprint,
                    guard.record_error(error),
                    tool=plan.tool,
                )
            self._trace(
                trace,
                "tool_result",
                tool=plan.tool,
                input_fingerprint=plan.fact_fingerprint,
                result_fingerprint=tool_result.result_fingerprint,
            )

        self._trace(trace, "finished", input_fingerprint=input_fingerprint)
        return CareerAgentGovernedLoopResult(
            status=CareerAgentGovernedLoopStatus.COMPLETED,
            tool_results=tuple(results),
            trace=tuple(trace),
        )

    @staticmethod
    def _trace(
        trace: list[CareerAgentGovernedLoopTraceEvent],
        event: str,
        *,
        input_fingerprint: str,
        tool: CareerAgentToolName | None = None,
        result_fingerprint: str | None = None,
        error_code: str | None = None,
    ) -> None:
        sequence = len(trace) + 1
        trace_fingerprint = _fingerprint(
            {
                "sequence": sequence,
                "event": event,
                "tool": tool.value if tool else None,
                "input": input_fingerprint,
                "result": result_fingerprint,
                "error": error_code,
            }
        )
        trace.append(
            CareerAgentGovernedLoopTraceEvent(
                sequence=sequence,
                event=event,
                tool=tool,
                input_fingerprint=input_fingerprint,
                result_fingerprint=result_fingerprint,
                error_code=error_code,
                trace_fingerprint=trace_fingerprint,
            )
        )

    def _failed(
        self,
        trace: list[CareerAgentGovernedLoopTraceEvent],
        results: list[AgentToolResult],
        input_fingerprint: str,
        error: CareerAgentLoopError,
        *,
        tool: CareerAgentToolName | None = None,
    ) -> CareerAgentGovernedLoopResult:
        self._trace(
            trace,
            "failed",
            input_fingerprint=input_fingerprint,
            tool=tool,
            error_code=error.code.value,
        )
        return CareerAgentGovernedLoopResult(
            status=CareerAgentGovernedLoopStatus.FAILED,
            tool_results=tuple(results),
            trace=tuple(trace),
            message=str(error),
            error_code=error.code.value,
        )


def _replace_intent_goals(
    intent: CareerIntent,
    goals: tuple[CareerIntentGoal, ...],
) -> CareerIntent:
    return CareerIntent(
        goals=goals,
        referenced_job_ids=intent.referenced_job_ids,
        current_job_required=intent.current_job_required,
        needs_clarification=intent.needs_clarification,
        clarification_question=intent.clarification_question,
        unsupported_request=intent.unsupported_request,
        confidence=intent.confidence,
        reasoning_summary=intent.reasoning_summary,
    )


def _index_plans(
    plans: tuple[CareerAgentPlannedToolRequest, ...],
) -> dict[CareerAgentToolName, CareerAgentPlannedToolRequest]:
    indexed: dict[CareerAgentToolName, CareerAgentPlannedToolRequest] = {}
    for plan in plans:
        if plan.tool in indexed:
            raise ValueError(f"duplicate planned request for tool: {plan.tool.value}")
        indexed[plan.tool] = plan
    return indexed


def _structured_success_result(*, tool: CareerAgentToolName, output: object) -> AgentToolResult:
    fingerprint = _fingerprint({"tool": tool.value, "output": output})
    return AgentToolResult(
        status=AgentToolResultStatus.SUCCESS,
        summary=f"{tool.value} completed successfully.",
        result_fingerprint=fingerprint,
    )


def _is_sha256_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=lambda item: getattr(item, "value", repr(item)),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "CareerAgentGovernedLoopResult",
    "CareerAgentGovernedLoopRuntime",
    "CareerAgentGovernedLoopStatus",
    "CareerAgentGovernedLoopTraceEvent",
    "CareerAgentLoopRecoveryPlanner",
    "CareerAgentPlannedToolRequest",
    "CareerAgentStalenessGuard",
    "CareerAgentUnknownToolReplanner",
]
