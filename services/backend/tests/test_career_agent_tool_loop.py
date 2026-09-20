import pytest

from app.agent.tool_loop import (
    CareerAgentLoopBudget,
    CareerAgentLoopDecision,
    CareerAgentLoopDecisionType,
    CareerAgentLoopError,
    CareerAgentLoopErrorCode,
    CareerAgentLoopGuard,
    CareerAgentLoopObservation,
)
from app.agent.tool_registry import CareerAgentToolName


def test_loop_budget_defaults_are_bounded_and_cannot_exceed_hard_limits() -> None:
    budget = CareerAgentLoopBudget()

    assert budget.max_turns == 6
    assert budget.max_tool_calls == 8
    assert budget.max_provider_calls == 0
    assert budget.max_retries == 1
    assert budget.max_same_tool_consecutive == 2
    assert budget.max_runtime_seconds == 90

    with pytest.raises(ValueError, match="hard max turns"):
        CareerAgentLoopBudget(max_turns=11)


def test_loop_guard_enforces_turn_and_provider_budgets() -> None:
    guard = CareerAgentLoopGuard(CareerAgentLoopBudget(max_turns=2, max_provider_calls=1))

    guard.record_turn()
    guard.record_turn()
    with pytest.raises(CareerAgentLoopError, match="turn budget") as turn_error:
        guard.record_turn()
    assert turn_error.value.code is CareerAgentLoopErrorCode.BUDGET_EXHAUSTED

    guard.record_provider_call()
    with pytest.raises(CareerAgentLoopError, match="provider-call budget") as provider_error:
        guard.record_provider_call()
    assert provider_error.value.code is CareerAgentLoopErrorCode.BUDGET_EXHAUSTED


def test_loop_decision_contract_rejects_invalid_control_actions() -> None:
    decision = CareerAgentLoopDecision.call_tool(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        arguments_fingerprint="args-v1",
    )

    assert decision.type is CareerAgentLoopDecisionType.CALL_TOOL
    assert decision.tool is CareerAgentToolName.RANK_MATCH_REPORTS

    with pytest.raises(ValueError, match="call_tool requires"):
        CareerAgentLoopDecision(type=CareerAgentLoopDecisionType.CALL_TOOL)


def test_unknown_tool_is_structured_and_only_one_replan_is_allowed() -> None:
    guard = CareerAgentLoopGuard()

    first = guard.record_error(CareerAgentLoopError.unknown_tool("not_registered"))
    assert first.code is CareerAgentLoopErrorCode.UNKNOWN_TOOL
    assert first.retryable is True

    second = guard.record_error(CareerAgentLoopError.unknown_tool("still_not_registered"))
    assert second.code is CareerAgentLoopErrorCode.UNKNOWN_TOOL
    assert second.retryable is False


def test_third_identical_tool_call_is_rejected_as_repeat_loop() -> None:
    guard = CareerAgentLoopGuard()
    decision = CareerAgentLoopDecision.call_tool(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        arguments_fingerprint="same-args",
    )

    guard.record_tool_call(decision, input_fingerprint="facts-v1", transient_retry=False)
    guard.record_tool_call(decision, input_fingerprint="facts-v1", transient_retry=True)

    with pytest.raises(CareerAgentLoopError, match="repeated tool call") as exc_info:
        guard.record_tool_call(decision, input_fingerprint="facts-v1", transient_retry=True)

    assert exc_info.value.code is CareerAgentLoopErrorCode.LOOP_DETECTED
    assert exc_info.value.retryable is False


def test_second_identical_tool_call_requires_explicit_transient_retry() -> None:
    guard = CareerAgentLoopGuard()
    decision = CareerAgentLoopDecision.call_tool(
        tool=CareerAgentToolName.JOB_PREPARATION,
        arguments_fingerprint="job-1",
    )

    guard.record_tool_call(decision, input_fingerprint="facts-v1", transient_retry=False)

    with pytest.raises(CareerAgentLoopError, match="transient retry") as exc_info:
        guard.record_tool_call(decision, input_fingerprint="facts-v1", transient_retry=False)

    assert exc_info.value.code is CareerAgentLoopErrorCode.LOOP_DETECTED


def test_two_observations_without_progress_stop_the_loop() -> None:
    guard = CareerAgentLoopGuard()
    observation = CareerAgentLoopObservation(
        state_fingerprint="state-v1",
        blocker_fingerprint="blocked-release-gate",
        fact_fingerprint="facts-v1",
    )

    guard.record_observation(observation)

    with pytest.raises(CareerAgentLoopError, match="no progress") as exc_info:
        guard.record_observation(observation)

    assert exc_info.value.code is CareerAgentLoopErrorCode.NO_PROGRESS
    assert exc_info.value.retryable is False
