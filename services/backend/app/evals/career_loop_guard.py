"""Deterministic vNext 1.1 Loop Guard Eval.

This module owns the Eval boundary only.  It drives Agent A's frozen Core
``CareerAgentLoopGuard`` through versioned, frozen step sequences and never
reimplements a budget, a stop condition, or a loop detector of its own.

Core already unit-tests each mechanism in isolation.  This gate adds what unit
tests cannot provide: a frozen all-cases cohort with release minimums, plus
cross-case invariants that a per-unit test cannot express.  Two of those
invariants are the reason this gate exists:

- **no false stops** -- an over-conservative guard that stops healthy progress is
  a product regression, and nothing in the Core unit suite would catch it;
- **no unclassified stops** -- every stop must arrive as a structured
  ``CareerAgentLoopError`` with a code, never as a leaked raw exception.

It also pins the exactly-at-budget boundary (using the budget in full is legal;
exceeding it stops) and proves retry budgets are tracked per error code rather
than globally.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from app.agent.tool_loop import (
    CareerAgentLoopBudget,
    CareerAgentLoopDecision,
    CareerAgentLoopError,
    CareerAgentLoopErrorCode,
    CareerAgentLoopGuard,
    CareerAgentLoopObservation,
)
from app.agent.tool_registry import CareerAgentToolName


class LoopGuardEvalCategory(StrEnum):
    MAX_TURNS = "max_turns"
    MAX_TOOL_CALLS = "max_tool_calls"
    PROVIDER_BUDGET = "provider_budget"
    RETRY_BOUND = "retry_bound"
    SAME_TOOL = "same_tool"
    NO_PROGRESS = "no_progress"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_TOOL_PARAMS = "invalid_tool_params"
    HEALTHY_PROGRESS = "healthy_progress"


class LoopGuardEvalStepType(StrEnum):
    TURN = "turn"
    PROVIDER_CALL = "provider_call"
    TOOL_CALL = "tool_call"
    OBSERVATION = "observation"
    ERROR = "error"


_RELEASE_MINIMUMS: dict[LoopGuardEvalCategory, int] = {
    LoopGuardEvalCategory.MAX_TURNS: 3,
    LoopGuardEvalCategory.MAX_TOOL_CALLS: 3,
    LoopGuardEvalCategory.PROVIDER_BUDGET: 2,
    LoopGuardEvalCategory.RETRY_BOUND: 3,
    LoopGuardEvalCategory.SAME_TOOL: 3,
    LoopGuardEvalCategory.NO_PROGRESS: 3,
    LoopGuardEvalCategory.UNKNOWN_TOOL: 3,
    LoopGuardEvalCategory.INVALID_TOOL_PARAMS: 3,
    LoopGuardEvalCategory.HEALTHY_PROGRESS: 3,
}
_RELEASE_MINIMUM_TOTAL = sum(_RELEASE_MINIMUMS.values())

_BUDGET_FIELDS = frozenset(field.name for field in fields(CareerAgentLoopBudget))

_REQUIRED_STOP_CODES: dict[LoopGuardEvalCategory, str] = {
    LoopGuardEvalCategory.MAX_TURNS: CareerAgentLoopErrorCode.BUDGET_EXHAUSTED.value,
    LoopGuardEvalCategory.MAX_TOOL_CALLS: CareerAgentLoopErrorCode.BUDGET_EXHAUSTED.value,
    LoopGuardEvalCategory.PROVIDER_BUDGET: CareerAgentLoopErrorCode.BUDGET_EXHAUSTED.value,
    LoopGuardEvalCategory.SAME_TOOL: CareerAgentLoopErrorCode.LOOP_DETECTED.value,
    LoopGuardEvalCategory.NO_PROGRESS: CareerAgentLoopErrorCode.NO_PROGRESS.value,
}

_NON_STOPPING_CATEGORIES = (
    LoopGuardEvalCategory.RETRY_BOUND,
    LoopGuardEvalCategory.UNKNOWN_TOOL,
    LoopGuardEvalCategory.INVALID_TOOL_PARAMS,
    LoopGuardEvalCategory.HEALTHY_PROGRESS,
)

_DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "evals"
    / "career-loop-guard"
    / "career-loop-guard-v1.jsonl"
)


@dataclass(frozen=True, slots=True)
class LoopGuardEvalStep:
    """One deterministic interaction with the Core loop guard."""

    type: LoopGuardEvalStepType
    tool: str | None = None
    arguments_fingerprint: str | None = None
    input_fingerprint: str | None = None
    transient_retry: bool = False
    state_fingerprint: str | None = None
    blocker_fingerprint: str | None = None
    fact_fingerprint: str | None = None
    error_code: str | None = None
    error_retryable: bool = False


@dataclass(frozen=True, slots=True)
class LoopGuardEvalExpected:
    """Assertions required of the Core loop guard for one frozen sequence."""

    stopped: bool
    stop_code: str | None = None
    stop_retryable: bool | None = None
    turns_used: int = 0
    tool_calls_used: int = 0
    provider_budget_used: int = 0
    retry_outcomes: tuple[tuple[str, bool], ...] = ()
    steps_applied: int = 0


@dataclass(frozen=True, slots=True)
class LoopGuardEvalCase:
    case_id: str
    category: LoopGuardEvalCategory
    budget_overrides: Mapping[str, int]
    steps: tuple[LoopGuardEvalStep, ...]
    expected: LoopGuardEvalExpected


@dataclass(frozen=True, slots=True)
class LoopGuardEvalExecution:
    """Observed guard behaviour plus the Eval safety budget counters."""

    stopped: bool
    stop_code: str | None = None
    stop_retryable: bool | None = None
    turns_used: int = 0
    tool_calls_used: int = 0
    provider_budget_used: int = 0
    retry_outcomes: tuple[tuple[str, bool], ...] = ()
    steps_applied: int = 0
    unclassified_error: str | None = None
    provider_attempts: int = 0
    provider_completed: int = 0
    business_writes: int = 0


@dataclass(frozen=True, slots=True)
class LoopGuardEvalCaseResult:
    case_id: str
    passed: bool
    failure_reasons: tuple[str, ...]
    execution: LoopGuardEvalExecution


@dataclass(frozen=True, slots=True)
class LoopGuardEvalReport:
    total_cases: int
    passed_cases: int
    failed_cases: int
    gate_passed: bool
    unclassified_errors: int
    retryable_stops: int
    healthy_cases_stopped: int
    provider_attempts: int
    provider_completed: int
    business_writes: int
    case_results: tuple[LoopGuardEvalCaseResult, ...]


class LoopGuardEvalDriver:
    """Apply a frozen step sequence to the real Core ``CareerAgentLoopGuard``.

    The driver contains no budget, retry, loop-detection or progress logic.  It
    only replays steps, counts the steps the guard accepted, and records the
    first structured stop.
    """

    def run(self, *, case: LoopGuardEvalCase) -> LoopGuardEvalExecution:
        guard = CareerAgentLoopGuard(_build_budget(case.budget_overrides))
        turns_used = 0
        tool_calls_used = 0
        provider_budget_used = 0
        retry_outcomes: list[tuple[str, bool]] = []
        steps_applied = 0

        for step in case.steps:
            try:
                retry_outcome = _apply_step(guard=guard, step=step)
            except CareerAgentLoopError as stop:
                return LoopGuardEvalExecution(
                    stopped=True,
                    stop_code=stop.code.value,
                    stop_retryable=stop.retryable,
                    turns_used=turns_used,
                    tool_calls_used=tool_calls_used,
                    provider_budget_used=provider_budget_used,
                    retry_outcomes=tuple(retry_outcomes),
                    steps_applied=steps_applied,
                )
            except Exception as exc:  # A raw failure is a governance violation.
                return LoopGuardEvalExecution(
                    stopped=True,
                    stop_code=None,
                    stop_retryable=None,
                    turns_used=turns_used,
                    tool_calls_used=tool_calls_used,
                    provider_budget_used=provider_budget_used,
                    retry_outcomes=tuple(retry_outcomes),
                    steps_applied=steps_applied,
                    unclassified_error=f"{type(exc).__name__}: {exc}",
                )

            if retry_outcome is not None:
                retry_outcomes.append(retry_outcome)
            if step.type is LoopGuardEvalStepType.TURN:
                turns_used += 1
            elif step.type is LoopGuardEvalStepType.TOOL_CALL:
                tool_calls_used += 1
            elif step.type is LoopGuardEvalStepType.PROVIDER_CALL:
                provider_budget_used += 1
            steps_applied += 1

        return LoopGuardEvalExecution(
            stopped=False,
            turns_used=turns_used,
            tool_calls_used=tool_calls_used,
            provider_budget_used=provider_budget_used,
            retry_outcomes=tuple(retry_outcomes),
            steps_applied=steps_applied,
        )


def _apply_step(
    *,
    guard: CareerAgentLoopGuard,
    step: LoopGuardEvalStep,
) -> tuple[str, bool] | None:
    if step.type is LoopGuardEvalStepType.TURN:
        guard.record_turn()
        return None
    if step.type is LoopGuardEvalStepType.PROVIDER_CALL:
        guard.record_provider_call()
        return None
    if step.type is LoopGuardEvalStepType.TOOL_CALL:
        assert step.tool is not None
        assert step.arguments_fingerprint is not None
        assert step.input_fingerprint is not None
        guard.record_tool_call(
            CareerAgentLoopDecision.call_tool(
                tool=CareerAgentToolName(step.tool),
                arguments_fingerprint=step.arguments_fingerprint,
            ),
            input_fingerprint=step.input_fingerprint,
            transient_retry=step.transient_retry,
        )
        return None
    if step.type is LoopGuardEvalStepType.OBSERVATION:
        assert step.state_fingerprint is not None
        assert step.blocker_fingerprint is not None
        assert step.fact_fingerprint is not None
        guard.record_observation(
            CareerAgentLoopObservation(
                state_fingerprint=step.state_fingerprint,
                blocker_fingerprint=step.blocker_fingerprint,
                fact_fingerprint=step.fact_fingerprint,
            )
        )
        return None

    assert step.type is LoopGuardEvalStepType.ERROR
    assert step.error_code is not None
    normalized = guard.record_error(
        CareerAgentLoopError(
            code=CareerAgentLoopErrorCode(step.error_code),
            message=f"eval step error: {step.error_code}",
            retryable=step.error_retryable,
        )
    )
    return (normalized.code.value, normalized.retryable)


def _build_budget(overrides: Mapping[str, int]) -> CareerAgentLoopBudget:
    return replace(CareerAgentLoopBudget(), **dict(overrides))


def load_career_loop_guard_eval_dataset(
    path: str | Path = _DEFAULT_DATASET_PATH,
) -> tuple[LoopGuardEvalCase, ...]:
    """Load a versioned JSONL cohort and enforce frozen release minimums."""

    dataset_path = Path(path)
    cases: list[LoopGuardEvalCase] = []
    case_ids: set[str] = set()
    for line_number, raw_line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid Loop Guard Eval JSONL at line {line_number}"
            ) from exc
        case = _parse_case(payload, line_number=line_number)
        if case.case_id in case_ids:
            raise ValueError(f"duplicate Loop Guard Eval case id: {case.case_id}")
        case_ids.add(case.case_id)
        cases.append(case)

    validate_career_loop_guard_release_dataset(tuple(cases))
    return tuple(cases)


def validate_career_loop_guard_release_dataset(
    cases: tuple[LoopGuardEvalCase, ...],
) -> None:
    """Prevent a smaller or category-skewed dataset from claiming the gate."""

    if len(cases) < _RELEASE_MINIMUM_TOTAL:
        raise ValueError(
            f"Loop Guard Eval requires at least {_RELEASE_MINIMUM_TOTAL} cases"
        )

    duplicate_ids = [
        case_id
        for case_id, count in Counter(case.case_id for case in cases).items()
        if count > 1
    ]
    if duplicate_ids:
        raise ValueError(
            "duplicate Loop Guard Eval case ids: " + ", ".join(sorted(duplicate_ids))
        )

    category_counts = Counter(case.category for case in cases)
    missing = [
        f"{category.value} >= {minimum} (got {category_counts[category]})"
        for category, minimum in _RELEASE_MINIMUMS.items()
        if category_counts[category] < minimum
    ]
    if missing:
        raise ValueError(
            "Loop Guard Eval dataset category minimums failed: " + "; ".join(missing)
        )


def evaluate_career_loop_guard(
    *,
    driver: LoopGuardEvalDriver,
    cases: tuple[LoopGuardEvalCase, ...],
    require_release_dataset: bool = True,
) -> LoopGuardEvalReport:
    """Evaluate the Core loop guard and enforce cross-case stop invariants."""

    if not cases:
        raise ValueError("Loop Guard Eval requires at least one case")
    if require_release_dataset:
        validate_career_loop_guard_release_dataset(cases)

    results = tuple(_evaluate_case(driver=driver, case=case) for case in cases)
    paired = tuple(zip(cases, results))
    passed_cases = sum(result.passed for result in results)
    unclassified_errors = sum(
        1 for _, result in paired if result.execution.unclassified_error is not None
    )
    retryable_stops = sum(
        1
        for _, result in paired
        if result.execution.stopped and result.execution.stop_retryable is True
    )
    healthy_cases_stopped = sum(
        1
        for case, result in paired
        if result.execution.stopped
        and case.category is LoopGuardEvalCategory.HEALTHY_PROGRESS
    )

    return LoopGuardEvalReport(
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=len(results) - passed_cases,
        gate_passed=(
            passed_cases == len(results)
            and unclassified_errors == 0
            and retryable_stops == 0
            and healthy_cases_stopped == 0
        ),
        unclassified_errors=unclassified_errors,
        retryable_stops=retryable_stops,
        healthy_cases_stopped=healthy_cases_stopped,
        provider_attempts=sum(result.execution.provider_attempts for result in results),
        provider_completed=sum(result.execution.provider_completed for result in results),
        business_writes=sum(result.execution.business_writes for result in results),
        case_results=results,
    )


def _evaluate_case(
    *,
    driver: LoopGuardEvalDriver,
    case: LoopGuardEvalCase,
) -> LoopGuardEvalCaseResult:
    failure_reasons: list[str] = []
    try:
        execution = driver.run(case=case)
    except Exception as exc:  # Driver failures must be represented per case.
        execution = LoopGuardEvalExecution(
            stopped=True,
            unclassified_error=f"driver raised {type(exc).__name__}: {exc}",
        )

    _assert_safety_budgets(execution=execution, failures=failure_reasons)
    _assert_execution_matches_expectation(execution=execution, case=case, failures=failure_reasons)

    return LoopGuardEvalCaseResult(
        case_id=case.case_id,
        passed=not failure_reasons,
        failure_reasons=tuple(failure_reasons),
        execution=execution,
    )


def _assert_safety_budgets(
    *,
    execution: LoopGuardEvalExecution,
    failures: list[str],
) -> None:
    if execution.unclassified_error is not None:
        failures.append(
            "unclassified error: the loop must fail with a structured "
            f"CareerAgentLoopError, got {execution.unclassified_error}"
        )
    for field_name, actual in (
        ("provider attempts", execution.provider_attempts),
        ("provider completed", execution.provider_completed),
        ("business writes", execution.business_writes),
    ):
        if actual != 0:
            failures.append(
                f"{field_name} must be 0 during deterministic Loop Guard Eval, got {actual}"
            )


def _assert_execution_matches_expectation(
    *,
    execution: LoopGuardEvalExecution,
    case: LoopGuardEvalCase,
    failures: list[str],
) -> None:
    expected = case.expected
    if execution.stopped != expected.stopped:
        failures.append(f"stopped expected {expected.stopped}, got {execution.stopped}")
    if execution.stop_code != expected.stop_code:
        failures.append(f"stop_code expected {expected.stop_code!r}, got {execution.stop_code!r}")
    if execution.stop_retryable != expected.stop_retryable:
        failures.append(
            f"stop_retryable expected {expected.stop_retryable!r}, "
            f"got {execution.stop_retryable!r}"
        )
    if execution.turns_used != expected.turns_used:
        failures.append(f"turns_used expected {expected.turns_used}, got {execution.turns_used}")
    if execution.tool_calls_used != expected.tool_calls_used:
        failures.append(
            f"tool_calls_used expected {expected.tool_calls_used}, "
            f"got {execution.tool_calls_used}"
        )
    if execution.provider_budget_used != expected.provider_budget_used:
        failures.append(
            "provider_budget_used expected "
            f"{expected.provider_budget_used}, got {execution.provider_budget_used}"
        )
    if execution.retry_outcomes != expected.retry_outcomes:
        failures.append(
            f"retry_outcomes expected {expected.retry_outcomes!r}, "
            f"got {execution.retry_outcomes!r}"
        )
    if execution.steps_applied != expected.steps_applied:
        failures.append(
            f"steps_applied expected {expected.steps_applied}, got {execution.steps_applied}"
        )
    if expected.stopped and execution.unclassified_error is None and execution.stop_code is None:
        failures.append("a stopped case must carry a structured stop code")


def _parse_case(payload: object, *, line_number: int) -> LoopGuardEvalCase:
    if not isinstance(payload, dict):
        raise ValueError(f"Loop Guard Eval line {line_number} must be an object")

    case_id = _required_string(payload, "id", line_number=line_number)
    category_raw = _required_string(payload, "category", line_number=line_number)
    try:
        category = LoopGuardEvalCategory(category_raw)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in LoopGuardEvalCategory)
        raise ValueError(
            f"Loop Guard Eval line {line_number} has invalid category "
            f"{category_raw!r}; expected one of {allowed}"
        ) from exc

    budget_overrides = _parse_budget(payload.get("budget", {}), line_number=line_number)
    steps_payload = payload.get("steps")
    if not isinstance(steps_payload, list) or not steps_payload:
        raise ValueError(
            f"Loop Guard Eval line {line_number} requires a non-empty steps array"
        )
    steps = tuple(
        _parse_step(step, line_number=line_number, index=index)
        for index, step in enumerate(steps_payload)
    )

    expected_payload = _object(payload.get("expected"), field="expected", line_number=line_number)
    stopped = _required_bool(expected_payload, "stopped", line_number=line_number)
    stop_code = _optional_string(
        expected_payload.get("stopCode"),
        field="expected.stopCode",
        line_number=line_number,
    )
    stop_retryable_raw = expected_payload.get("stopRetryable")
    if stop_retryable_raw is not None and not isinstance(stop_retryable_raw, bool):
        raise ValueError(
            f"Loop Guard Eval line {line_number} field expected.stopRetryable must be bool | null"
        )
    if stopped and stop_code is None:
        raise ValueError(f"{case_id}: a stopped case requires expected.stopCode")
    if not stopped and (stop_code is not None or stop_retryable_raw is not None):
        raise ValueError(
            f"{case_id}: a non-stopped case must not declare stopCode or stopRetryable"
        )

    expected = LoopGuardEvalExpected(
        stopped=stopped,
        stop_code=stop_code,
        stop_retryable=stop_retryable_raw,
        turns_used=_required_int(expected_payload, "turnsUsed", line_number=line_number),
        tool_calls_used=_required_int(
            expected_payload, "toolCallsUsed", line_number=line_number
        ),
        provider_budget_used=_required_int(
            expected_payload, "providerBudgetUsed", line_number=line_number
        ),
        retry_outcomes=_retry_outcomes(
            expected_payload.get("retryOutcomes", []),
            line_number=line_number,
        ),
        steps_applied=_required_int(expected_payload, "stepsApplied", line_number=line_number),
    )

    case = LoopGuardEvalCase(
        case_id=case_id,
        category=category,
        budget_overrides=budget_overrides,
        steps=steps,
        expected=expected,
    )
    _validate_case_semantics(case)
    return case


def _validate_case_semantics(case: LoopGuardEvalCase) -> None:
    case_id = case.case_id
    expected = case.expected

    if expected.steps_applied > len(case.steps):
        raise ValueError(
            f"{case_id}: stepsApplied cannot exceed the number of declared steps"
        )
    if not expected.stopped and expected.steps_applied != len(case.steps):
        raise ValueError(f"{case_id}: a non-stopped case must apply every step")

    if case.category is LoopGuardEvalCategory.HEALTHY_PROGRESS:
        if expected.stopped:
            raise ValueError(f"{case_id}: healthy_progress case must not expect a stop")
    elif case.category in _NON_STOPPING_CATEGORIES:
        if expected.stopped:
            raise ValueError(
                f"{case_id}: {case.category.value} case must not expect a stop because "
                "record_error never raises"
            )
    else:
        required_code = _REQUIRED_STOP_CODES.get(case.category)
        if expected.stopped and required_code is not None and expected.stop_code != required_code:
            raise ValueError(
                f"{case_id}: {case.category.value} case must stop with {required_code}"
            )

    if expected.provider_budget_used > case.budget_overrides.get(
        "max_provider_calls", CareerAgentLoopBudget().max_provider_calls
    ):
        raise ValueError(f"{case_id}: providerBudgetUsed exceeds the declared budget")

    retry_categories = (
        LoopGuardEvalCategory.RETRY_BOUND,
        LoopGuardEvalCategory.UNKNOWN_TOOL,
        LoopGuardEvalCategory.INVALID_TOOL_PARAMS,
    )
    if expected.retry_outcomes and case.category not in retry_categories:
        raise ValueError(
            f"{case_id}: retryOutcomes are only meaningful for error-classification cases"
        )
    if case.category in retry_categories and len(expected.retry_outcomes) != sum(
        1 for step in case.steps if step.type is LoopGuardEvalStepType.ERROR
    ):
        raise ValueError(
            f"{case_id}: retryOutcomes must report one outcome per error step"
        )


def _parse_budget(payload: object, *, line_number: int) -> dict[str, int]:
    budget_payload = _object(payload, field="budget", line_number=line_number)
    overrides: dict[str, int] = {}
    for key, value in budget_payload.items():
        if key not in _BUDGET_FIELDS:
            raise ValueError(
                f"Loop Guard Eval line {line_number} budget has unknown field {key!r}"
            )
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"Loop Guard Eval line {line_number} budget field {key} must be int"
            )
        overrides[key] = value
    return overrides


def _parse_step(payload: object, *, line_number: int, index: int) -> LoopGuardEvalStep:
    step_payload = _object(payload, field=f"steps[{index}]", line_number=line_number)
    type_raw = step_payload.get("type")
    try:
        step_type = LoopGuardEvalStepType(type_raw)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in LoopGuardEvalStepType)
        raise ValueError(
            f"Loop Guard Eval line {line_number} steps[{index}] has invalid step type "
            f"{type_raw!r}; expected one of {allowed}"
        ) from exc

    if step_type is LoopGuardEvalStepType.TOOL_CALL:
        tool_raw = _required_string(step_payload, "tool", line_number=line_number)
        try:
            CareerAgentToolName(tool_raw)
        except ValueError as exc:
            raise ValueError(
                f"Loop Guard Eval line {line_number} steps[{index}] references unknown tool "
                f"{tool_raw!r}"
            ) from exc
        return LoopGuardEvalStep(
            type=step_type,
            tool=tool_raw,
            arguments_fingerprint=_required_string(
                step_payload, "argumentsFingerprint", line_number=line_number
            ),
            input_fingerprint=_required_string(
                step_payload, "inputFingerprint", line_number=line_number
            ),
            transient_retry=_required_bool(
                step_payload, "transientRetry", line_number=line_number
            ),
        )

    if step_type is LoopGuardEvalStepType.OBSERVATION:
        return LoopGuardEvalStep(
            type=step_type,
            state_fingerprint=_required_string(
                step_payload, "stateFingerprint", line_number=line_number
            ),
            blocker_fingerprint=_required_string(
                step_payload, "blockerFingerprint", line_number=line_number
            ),
            fact_fingerprint=_required_string(
                step_payload, "factFingerprint", line_number=line_number
            ),
        )

    if step_type is LoopGuardEvalStepType.ERROR:
        code_raw = _required_string(step_payload, "errorCode", line_number=line_number)
        try:
            CareerAgentLoopErrorCode(code_raw)
        except ValueError as exc:
            raise ValueError(
                f"Loop Guard Eval line {line_number} steps[{index}] references unknown "
                f"error code {code_raw!r}"
            ) from exc
        return LoopGuardEvalStep(
            type=step_type,
            error_code=code_raw,
            error_retryable=_required_bool(
                step_payload, "errorRetryable", line_number=line_number
            ),
        )

    return LoopGuardEvalStep(type=step_type)


def _required_string(payload: Mapping[str, object], field: str, *, line_number: int) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Loop Guard Eval line {line_number} requires non-empty {field}"
        )
    return value


def _optional_string(value: object, *, field: str, line_number: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Loop Guard Eval line {line_number} field {field} must be non-empty str | null"
        )
    return value


def _object(value: object, *, field: str, line_number: int) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(
            f"Loop Guard Eval line {line_number} field {field} must be an object"
        )
    return value


def _required_bool(payload: Mapping[str, object], field: str, *, line_number: int) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"Loop Guard Eval line {line_number} field {field} must be bool")
    return value


def _required_int(payload: Mapping[str, object], field: str, *, line_number: int) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Loop Guard Eval line {line_number} field {field} must be int")
    return value


def _retry_outcomes(value: object, *, line_number: int) -> tuple[tuple[str, bool], ...]:
    if not isinstance(value, list):
        raise ValueError(
            f"Loop Guard Eval line {line_number} field expected.retryOutcomes must be an array"
        )
    outcomes: list[tuple[str, bool]] = []
    for entry in value:
        if (
            not isinstance(entry, list)
            or len(entry) != 2
            or not isinstance(entry[0], str)
            or not isinstance(entry[1], bool)
        ):
            raise ValueError(
                f"Loop Guard Eval line {line_number} retryOutcomes entries must be "
                "[code, retryable] pairs"
            )
        outcomes.append((entry[0], entry[1]))
    return tuple(outcomes)


__all__ = [
    "LoopGuardEvalCase",
    "LoopGuardEvalCaseResult",
    "LoopGuardEvalCategory",
    "LoopGuardEvalDriver",
    "LoopGuardEvalExecution",
    "LoopGuardEvalExpected",
    "LoopGuardEvalReport",
    "LoopGuardEvalStep",
    "LoopGuardEvalStepType",
    "evaluate_career_loop_guard",
    "load_career_loop_guard_eval_dataset",
    "validate_career_loop_guard_release_dataset",
]
