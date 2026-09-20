"""Bounded control contracts and loop guards for Career Agent vNext 1.1.

This module owns runtime limits and deterministic stop conditions only. It does
not choose tools, call a model, or classify workflow/provider failures beyond
the small retry counters needed to keep the loop bounded.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.agent.tool_registry import CareerAgentToolName


class CareerAgentLoopDecisionType(StrEnum):
    CALL_TOOL = "call_tool"
    ASK_CLARIFICATION = "ask_clarification"
    REQUEST_HUMAN_ACTION = "request_human_action"
    FINISH = "finish"


class CareerAgentLoopErrorCode(StrEnum):
    INVALID_INTENT_OUTPUT = "invalid_intent_output"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_TOOL_PARAMS = "invalid_tool_params"
    LOOP_DETECTED = "loop_detected"
    NO_PROGRESS = "no_progress"
    BUDGET_EXHAUSTED = "budget_exhausted"


class CareerAgentLoopError(ValueError):
    """Structured deterministic loop failure safe to persist in trace metadata."""

    def __init__(self, *, code: CareerAgentLoopErrorCode, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    @classmethod
    def unknown_tool(cls, tool: str) -> "CareerAgentLoopError":
        return cls(
            code=CareerAgentLoopErrorCode.UNKNOWN_TOOL,
            message=f"unknown Career Agent tool: {tool}",
            retryable=True,
        )

    @classmethod
    def invalid_tool_params(cls, tool: CareerAgentToolName) -> "CareerAgentLoopError":
        return cls(
            code=CareerAgentLoopErrorCode.INVALID_TOOL_PARAMS,
            message=f"invalid parameters for Career Agent tool: {tool.value}",
            retryable=True,
        )


@dataclass(frozen=True, slots=True)
class CareerAgentLoopBudget:
    max_turns: int = 6
    max_tool_calls: int = 8
    max_provider_calls: int = 0
    max_retries: int = 1
    max_same_tool_consecutive: int = 2
    max_runtime_seconds: int = 90

    HARD_MAX_TURNS = 10

    def __post_init__(self) -> None:
        values = (
            self.max_turns,
            self.max_tool_calls,
            self.max_same_tool_consecutive,
            self.max_runtime_seconds,
        )
        if any(value <= 0 for value in values):
            raise ValueError("Career Agent loop limits must be positive")
        if self.max_provider_calls < 0 or self.max_retries < 0:
            raise ValueError("Career Agent provider/retry limits cannot be negative")
        if self.max_turns > self.HARD_MAX_TURNS:
            raise ValueError("Career Agent max_turns exceeds hard max turns")
        if self.max_same_tool_consecutive > self.max_tool_calls:
            raise ValueError("same-tool limit cannot exceed max_tool_calls")


@dataclass(frozen=True, slots=True)
class CareerAgentLoopDecision:
    type: CareerAgentLoopDecisionType
    tool: CareerAgentToolName | None = None
    arguments_fingerprint: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.type is CareerAgentLoopDecisionType.CALL_TOOL:
            if self.tool is None or not self.arguments_fingerprint:
                raise ValueError("call_tool requires tool and arguments_fingerprint")
        elif self.tool is not None or self.arguments_fingerprint is not None:
            raise ValueError("non-tool loop decision cannot carry tool arguments")
        if self.type in (
            CareerAgentLoopDecisionType.ASK_CLARIFICATION,
            CareerAgentLoopDecisionType.REQUEST_HUMAN_ACTION,
        ) and not self.message:
            raise ValueError(f"{self.type.value} requires a message")

    @classmethod
    def call_tool(
        cls,
        *,
        tool: CareerAgentToolName,
        arguments_fingerprint: str,
    ) -> "CareerAgentLoopDecision":
        return cls(
            type=CareerAgentLoopDecisionType.CALL_TOOL,
            tool=tool,
            arguments_fingerprint=arguments_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class CareerAgentLoopObservation:
    state_fingerprint: str
    blocker_fingerprint: str
    fact_fingerprint: str


class CareerAgentLoopGuard:
    """Enforce bounded retries, repeat-call detection, and no-progress stops."""

    def __init__(self, budget: CareerAgentLoopBudget | None = None) -> None:
        self._budget = budget or CareerAgentLoopBudget()
        self._turns = 0
        self._tool_calls = 0
        self._provider_calls = 0
        self._retry_counts: dict[CareerAgentLoopErrorCode, int] = {}
        self._last_call_key: tuple[CareerAgentToolName, str, str] | None = None
        self._same_call_count = 0
        self._last_observation: CareerAgentLoopObservation | None = None

    def record_turn(self) -> None:
        if self._turns >= self._budget.max_turns:
            raise CareerAgentLoopError(
                code=CareerAgentLoopErrorCode.BUDGET_EXHAUSTED,
                message="Career Agent turn budget exhausted",
                retryable=False,
            )
        self._turns += 1

    def record_provider_call(self) -> None:
        if self._provider_calls >= self._budget.max_provider_calls:
            raise CareerAgentLoopError(
                code=CareerAgentLoopErrorCode.BUDGET_EXHAUSTED,
                message="Career Agent provider-call budget exhausted",
                retryable=False,
            )
        self._provider_calls += 1

    def record_error(self, error: CareerAgentLoopError) -> CareerAgentLoopError:
        count = self._retry_counts.get(error.code, 0)
        self._retry_counts[error.code] = count + 1
        if not error.retryable or count >= self._budget.max_retries:
            return CareerAgentLoopError(code=error.code, message=str(error), retryable=False)
        return error

    def record_tool_call(
        self,
        decision: CareerAgentLoopDecision,
        *,
        input_fingerprint: str,
        transient_retry: bool,
    ) -> None:
        if decision.type is not CareerAgentLoopDecisionType.CALL_TOOL:
            raise ValueError("record_tool_call requires a call_tool decision")
        if self._tool_calls >= self._budget.max_tool_calls:
            raise CareerAgentLoopError(
                code=CareerAgentLoopErrorCode.BUDGET_EXHAUSTED,
                message="Career Agent tool-call budget exhausted",
                retryable=False,
            )

        assert decision.tool is not None
        assert decision.arguments_fingerprint is not None
        key = (decision.tool, decision.arguments_fingerprint, input_fingerprint)
        same_call_count = self._same_call_count + 1 if key == self._last_call_key else 1
        if same_call_count > 1 and not transient_retry:
            raise CareerAgentLoopError(
                code=CareerAgentLoopErrorCode.LOOP_DETECTED,
                message="repeated tool call requires an explicit transient retry",
                retryable=False,
            )
        if same_call_count > self._budget.max_same_tool_consecutive:
            raise CareerAgentLoopError(
                code=CareerAgentLoopErrorCode.LOOP_DETECTED,
                message="repeated tool call exceeded the bounded retry limit",
                retryable=False,
            )

        self._tool_calls += 1
        self._last_call_key = key
        self._same_call_count = same_call_count

    def record_observation(self, observation: CareerAgentLoopObservation) -> None:
        if self._last_observation == observation:
            raise CareerAgentLoopError(
                code=CareerAgentLoopErrorCode.NO_PROGRESS,
                message="Career Agent made no progress across consecutive tool results",
                retryable=False,
            )
        self._last_observation = observation


__all__ = [
    "CareerAgentLoopBudget",
    "CareerAgentLoopDecision",
    "CareerAgentLoopDecisionType",
    "CareerAgentLoopError",
    "CareerAgentLoopErrorCode",
    "CareerAgentLoopGuard",
    "CareerAgentLoopObservation",
]
