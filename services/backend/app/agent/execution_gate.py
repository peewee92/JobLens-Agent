"""Effect, cost, and human-approval gate for Career Agent tool execution.

The gate is deliberately evaluated before workflow invocation.  It does not
approve actions itself; anything outside the vNext 1.1 auto-execution envelope
is converted into a compact PendingAction for the durable HITL runtime.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from app.agent.context import CareerAgentContext
from app.agent.tool_registry import (
    CareerAgentHumanGateRequirement,
    CareerAgentProviderCostClass,
    CareerAgentSideEffectClass,
    CareerAgentToolDefinition,
    CareerAgentToolName,
    CareerAgentToolRegistry,
    CareerAgentToolRequest,
)


class CareerAgentExecutionGateOutcome(StrEnum):
    ALLOW = "allow"
    PENDING_ACTION = "pending_action"


class CareerAgentExecutionGateError(ValueError):
    """Raised when execution metadata is incomplete or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class CareerAgentPendingAction:
    action_type: str
    tool: CareerAgentToolName
    normalized_params: tuple[tuple[str, str], ...]
    why: str
    cost_class: CareerAgentProviderCostClass
    expected_provider_calls: int
    business_writes: int
    external_effects: tuple[str, ...]
    fact_fingerprint: str
    expires_at: str
    action_fingerprint: str


@dataclass(frozen=True, slots=True)
class CareerAgentExecutionGateDecision:
    outcome: CareerAgentExecutionGateOutcome
    pending_action: CareerAgentPendingAction | None = None

    def __post_init__(self) -> None:
        if self.outcome is CareerAgentExecutionGateOutcome.ALLOW and self.pending_action is not None:
            raise ValueError("allowed execution cannot carry a pending action")
        if self.outcome is CareerAgentExecutionGateOutcome.PENDING_ACTION and self.pending_action is None:
            raise ValueError("pending execution requires a pending action")


@dataclass(frozen=True, slots=True)
class CareerAgentGovernedToolExecutionResult:
    gate: CareerAgentExecutionGateDecision
    output: object | None = None


class CareerAgentExecutionGate:
    """Allow only zero-cost, no-gate read/transient tools to auto-execute."""

    MAX_NORMALIZED_PARAMS = 32
    MAX_PARAM_CHARS = 512
    MAX_EXTERNAL_EFFECTS = 16

    def evaluate(
        self,
        *,
        definition: CareerAgentToolDefinition,
        normalized_params: tuple[tuple[str, str], ...],
        fact_fingerprint: str,
        expected_provider_calls: int = 0,
        business_writes: int = 0,
        external_effects: tuple[str, ...] = (),
        expires_at: str | None = None,
    ) -> CareerAgentExecutionGateDecision:
        self._validate_inputs(
            definition=definition,
            normalized_params=normalized_params,
            fact_fingerprint=fact_fingerprint,
            expected_provider_calls=expected_provider_calls,
            business_writes=business_writes,
            external_effects=external_effects,
        )

        auto_executable = (
            definition.side_effect_class
            in (CareerAgentSideEffectClass.READ_ONLY, CareerAgentSideEffectClass.TRANSIENT_COMPUTE)
            and definition.provider_cost_class is CareerAgentProviderCostClass.NONE
            and definition.human_gate_requirement is CareerAgentHumanGateRequirement.NONE
            and expected_provider_calls == 0
            and business_writes == 0
            and not external_effects
        )
        if auto_executable:
            return CareerAgentExecutionGateDecision(CareerAgentExecutionGateOutcome.ALLOW)

        if not expires_at:
            raise CareerAgentExecutionGateError("gated tool execution requires expires_at")

        normalized_params = tuple(sorted(normalized_params))
        fingerprint_payload = {
            "tool": definition.name.value,
            "params": normalized_params,
            "side_effect_class": definition.side_effect_class.value,
            "cost_class": definition.provider_cost_class.value,
            "human_gate": definition.human_gate_requirement.value,
            "expected_provider_calls": expected_provider_calls,
            "business_writes": business_writes,
            "external_effects": external_effects,
            "fact_fingerprint": fact_fingerprint,
            "expires_at": expires_at,
        }
        action_fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        pending = CareerAgentPendingAction(
            action_type="tool_execution",
            tool=definition.name,
            normalized_params=normalized_params,
            why=self._pending_reason(definition),
            cost_class=definition.provider_cost_class,
            expected_provider_calls=expected_provider_calls,
            business_writes=business_writes,
            external_effects=external_effects,
            fact_fingerprint=fact_fingerprint,
            expires_at=expires_at,
            action_fingerprint=action_fingerprint,
        )
        return CareerAgentExecutionGateDecision(
            outcome=CareerAgentExecutionGateOutcome.PENDING_ACTION,
            pending_action=pending,
        )

    def _validate_inputs(
        self,
        *,
        definition: CareerAgentToolDefinition,
        normalized_params: tuple[tuple[str, str], ...],
        fact_fingerprint: str,
        expected_provider_calls: int,
        business_writes: int,
        external_effects: tuple[str, ...],
    ) -> None:
        if not fact_fingerprint:
            raise CareerAgentExecutionGateError("execution gate requires fact_fingerprint")
        if expected_provider_calls < 0 or business_writes < 0:
            raise CareerAgentExecutionGateError("effect counts cannot be negative")
        if len(normalized_params) > self.MAX_NORMALIZED_PARAMS or any(
            not key or len(key) > self.MAX_PARAM_CHARS or len(value) > self.MAX_PARAM_CHARS
            for key, value in normalized_params
        ):
            raise CareerAgentExecutionGateError("normalized parameters must be bounded")
        if len(external_effects) > self.MAX_EXTERNAL_EFFECTS or any(
            not effect or len(effect) > self.MAX_PARAM_CHARS for effect in external_effects
        ):
            raise CareerAgentExecutionGateError("external effects must be bounded")

        if definition.side_effect_class is CareerAgentSideEffectClass.PROVIDER_COMPUTE:
            if expected_provider_calls <= 0 or definition.provider_cost_class is CareerAgentProviderCostClass.NONE:
                raise CareerAgentExecutionGateError(
                    "provider compute requires bounded provider cost and expected provider calls"
                )
        elif expected_provider_calls > 0:
            raise CareerAgentExecutionGateError(
                "non-provider tool cannot declare expected provider calls"
            )

        if definition.side_effect_class is CareerAgentSideEffectClass.BUSINESS_WRITE:
            if business_writes <= 0:
                raise CareerAgentExecutionGateError("business write tool requires a positive write count")
        elif business_writes > 0:
            raise CareerAgentExecutionGateError("non-business-write tool cannot declare business writes")

        if definition.side_effect_class is CareerAgentSideEffectClass.EXTERNAL_ACTION:
            if not external_effects:
                raise CareerAgentExecutionGateError("external action requires explicit external effects")
        elif external_effects:
            raise CareerAgentExecutionGateError("non-external tool cannot declare external effects")

    @staticmethod
    def _pending_reason(definition: CareerAgentToolDefinition) -> str:
        if definition.side_effect_class is CareerAgentSideEffectClass.PROVIDER_COMPUTE:
            return "Provider compute requires bounded cost approval before execution."
        if definition.side_effect_class is CareerAgentSideEffectClass.BUSINESS_WRITE:
            return "Business state write requires explicit human approval before execution."
        if definition.side_effect_class is CareerAgentSideEffectClass.EXTERNAL_ACTION:
            return "External action requires explicit human approval before execution."
        return "Tool policy requires explicit human approval before execution."


class CareerAgentGovernedToolExecutor:
    """Apply execution policy before delegating to the existing Tool Registry."""

    def __init__(
        self,
        *,
        registry: CareerAgentToolRegistry,
        gate: CareerAgentExecutionGate | None = None,
    ) -> None:
        self._registry = registry
        self._gate = gate or CareerAgentExecutionGate()

    def execute(
        self,
        *,
        context: CareerAgentContext,
        tool: CareerAgentToolName,
        request: CareerAgentToolRequest,
        normalized_params: tuple[tuple[str, str], ...],
        fact_fingerprint: str,
        expected_provider_calls: int = 0,
        business_writes: int = 0,
        external_effects: tuple[str, ...] = (),
        expires_at: str | None = None,
    ) -> CareerAgentGovernedToolExecutionResult:
        definition = self._registry.definition(tool)
        gate_decision = self._gate.evaluate(
            definition=definition,
            normalized_params=normalized_params,
            fact_fingerprint=fact_fingerprint,
            expected_provider_calls=expected_provider_calls,
            business_writes=business_writes,
            external_effects=external_effects,
            expires_at=expires_at,
        )
        if gate_decision.outcome is CareerAgentExecutionGateOutcome.PENDING_ACTION:
            return CareerAgentGovernedToolExecutionResult(gate=gate_decision)
        output = self._registry.invoke(context=context, tool=tool, request=request)
        return CareerAgentGovernedToolExecutionResult(gate=gate_decision, output=output)


__all__ = [
    "CareerAgentExecutionGate",
    "CareerAgentExecutionGateDecision",
    "CareerAgentExecutionGateError",
    "CareerAgentExecutionGateOutcome",
    "CareerAgentGovernedToolExecutionResult",
    "CareerAgentGovernedToolExecutor",
    "CareerAgentPendingAction",
]
