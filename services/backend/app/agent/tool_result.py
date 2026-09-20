"""Structured Tool Result and bounded context references for Career Agent vNext 1.1."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AgentToolResultStatus(StrEnum):
    SUCCESS = "success"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class AgentContextTier(StrEnum):
    P0 = "p0"
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


@dataclass(frozen=True, slots=True)
class AgentContextRef:
    tier: AgentContextTier
    entity_id: str
    version: str
    fingerprint: str

    def __post_init__(self) -> None:
        if not self.entity_id or not self.version or not self.fingerprint:
            raise ValueError("context ref requires identity, version, and fingerprint")


@dataclass(frozen=True, slots=True)
class AgentToolResult:
    status: AgentToolResultStatus
    summary: str
    data_refs: tuple[AgentContextRef, ...] = ()
    grounding_refs: tuple[AgentContextRef, ...] = ()
    blockers: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()
    provider_calls: int = 0
    retryable: bool = False
    result_fingerprint: str = ""

    MAX_SUMMARY_CHARS = 1000
    MAX_REFS = 64
    MAX_BLOCKERS = 16

    def __post_init__(self) -> None:
        if not self.summary or len(self.summary) > self.MAX_SUMMARY_CHARS:
            raise ValueError("tool result summary must be present and bounded")
        if self.provider_calls < 0:
            raise ValueError("provider_calls cannot be negative")
        if not self.result_fingerprint:
            raise ValueError("tool result requires result_fingerprint")
        if len(self.data_refs) + len(self.grounding_refs) > self.MAX_REFS:
            raise ValueError("tool result context refs exceed bounded limit")
        if len(self.blockers) > self.MAX_BLOCKERS:
            raise ValueError("tool result blockers exceed bounded limit")


class CareerAgentErrorClass(StrEnum):
    INVALID_TOOL_PARAMS = "invalid_tool_params"
    UNKNOWN_TOOL = "unknown_tool"
    PERMISSION_OR_RELEASE_GATE = "permission_or_release_gate"
    STALE_STATE = "stale_state"
    TRANSIENT_NETWORK = "transient_network"
    PROVIDER_TRANSIENT = "provider_transient"
    WORKFLOW_INVARIANT = "workflow_invariant"
    CLARIFICATION_REQUIRED = "clarification_required"
    EFFECT_APPROVAL_REQUIRED = "effect_approval_required"
    CONTEXT_BUDGET_EXCEEDED = "context_budget_exceeded"


class CareerAgentErrorDisposition(StrEnum):
    REPLAN_ONCE = "replan_once"
    BLOCK = "block"
    ABORT_RUN = "abort_run"
    RETRY_BOUNDED = "retry_bounded"
    RETRY_EXISTING_POLICY = "retry_existing_policy"
    FAIL = "fail"
    ASK_CLARIFICATION = "ask_clarification"
    PENDING_ACTION = "pending_action"
    COMPACT_REFS = "compact_refs"


@dataclass(frozen=True, slots=True)
class CareerAgentErrorPolicy:
    error_class: CareerAgentErrorClass
    disposition: CareerAgentErrorDisposition
    retryable: bool
    max_retries: int = 0


class CareerAgentErrorClassifier:
    def classify(self, error_class: CareerAgentErrorClass) -> CareerAgentErrorPolicy:
        return _ERROR_POLICIES[error_class]


_ERROR_POLICIES = {
    CareerAgentErrorClass.INVALID_TOOL_PARAMS: CareerAgentErrorPolicy(CareerAgentErrorClass.INVALID_TOOL_PARAMS, CareerAgentErrorDisposition.REPLAN_ONCE, True, 1),
    CareerAgentErrorClass.UNKNOWN_TOOL: CareerAgentErrorPolicy(CareerAgentErrorClass.UNKNOWN_TOOL, CareerAgentErrorDisposition.REPLAN_ONCE, True, 1),
    CareerAgentErrorClass.PERMISSION_OR_RELEASE_GATE: CareerAgentErrorPolicy(CareerAgentErrorClass.PERMISSION_OR_RELEASE_GATE, CareerAgentErrorDisposition.BLOCK, False),
    CareerAgentErrorClass.STALE_STATE: CareerAgentErrorPolicy(CareerAgentErrorClass.STALE_STATE, CareerAgentErrorDisposition.ABORT_RUN, False),
    CareerAgentErrorClass.TRANSIENT_NETWORK: CareerAgentErrorPolicy(CareerAgentErrorClass.TRANSIENT_NETWORK, CareerAgentErrorDisposition.RETRY_BOUNDED, True, 1),
    CareerAgentErrorClass.PROVIDER_TRANSIENT: CareerAgentErrorPolicy(CareerAgentErrorClass.PROVIDER_TRANSIENT, CareerAgentErrorDisposition.RETRY_EXISTING_POLICY, True, 1),
    CareerAgentErrorClass.WORKFLOW_INVARIANT: CareerAgentErrorPolicy(CareerAgentErrorClass.WORKFLOW_INVARIANT, CareerAgentErrorDisposition.FAIL, False),
    CareerAgentErrorClass.CLARIFICATION_REQUIRED: CareerAgentErrorPolicy(CareerAgentErrorClass.CLARIFICATION_REQUIRED, CareerAgentErrorDisposition.ASK_CLARIFICATION, False),
    CareerAgentErrorClass.EFFECT_APPROVAL_REQUIRED: CareerAgentErrorPolicy(CareerAgentErrorClass.EFFECT_APPROVAL_REQUIRED, CareerAgentErrorDisposition.PENDING_ACTION, False),
    CareerAgentErrorClass.CONTEXT_BUDGET_EXCEEDED: CareerAgentErrorPolicy(CareerAgentErrorClass.CONTEXT_BUDGET_EXCEEDED, CareerAgentErrorDisposition.COMPACT_REFS, True),
}
