"""Deterministic vNext 1.1 CareerIntent dataset Eval.

This module owns the Eval boundary only.  It deliberately accepts an injected,
Core-owned natural-language router and never interprets user messages itself.
The runner compares structured router output against a versioned frozen cohort,
enforces grounded job scope, and fails closed for provider or business-write
activity during Intent Eval.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from app.agent.intent import (
    CareerIntentGoal,
    CareerIntentResolutionContext,
    CareerIntentRouter,
)


class IntentEvalCategory(StrEnum):
    SINGLE_GOAL = "single_goal"
    MULTI_GOAL = "multi_goal"
    CURRENT_JOB_PRONOUN = "current_job_pronoun"
    CLARIFICATION = "clarification"
    UNSUPPORTED_UNSAFE = "unsupported_unsafe"


_RELEASE_MINIMUMS: dict[IntentEvalCategory, int] = {
    IntentEvalCategory.SINGLE_GOAL: 15,
    IntentEvalCategory.MULTI_GOAL: 15,
    IntentEvalCategory.CURRENT_JOB_PRONOUN: 10,
    IntentEvalCategory.CLARIFICATION: 10,
    IntentEvalCategory.UNSUPPORTED_UNSAFE: 10,
}
_RELEASE_MINIMUM_TOTAL = sum(_RELEASE_MINIMUMS.values())
_DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "evals"
    / "career-intent"
    / "career-intent-v1.jsonl"
)


@dataclass(frozen=True, slots=True)
class IntentEvalContext:
    """Grounded identifiers authorized for a single intent evaluation turn."""

    current_job_id: str | None = None
    run_job_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IntentEvalExpected:
    """Assertions required of the injected Core intent implementation."""

    goals: tuple[str, ...]
    referenced_job_ids: tuple[str, ...] = ()
    current_job_required: bool = False
    needs_clarification: bool = False
    clarification_question_contains: str | None = None
    unsupported_request: str | None = None


@dataclass(frozen=True, slots=True)
class IntentEvalCase:
    case_id: str
    category: IntentEvalCategory
    message: str
    context: IntentEvalContext
    expected: IntentEvalExpected


@dataclass(frozen=True, slots=True)
class IntentEvalExecution:
    """Router result plus observable side-effect counters for Eval safety."""

    intent: object
    provider_attempts: int = 0
    provider_completed: int = 0
    business_writes: int = 0


class IntentEvalRouter(Protocol):
    """Core-owned NL router seam consumed by this Eval; never implemented here."""

    def route(self, *, message: str, context: IntentEvalContext) -> IntentEvalExecution: ...


class CareerIntentCoreEvalAdapter:
    """Thin adapter from the Core Router contract to the Eval runner seam."""

    def __init__(self, *, router: CareerIntentRouter) -> None:
        self._router = router

    def route(self, *, message: str, context: IntentEvalContext) -> IntentEvalExecution:
        intent = self._router.route(
            user_message=message,
            context=CareerIntentResolutionContext(
                current_job_id=context.current_job_id,
                run_job_ids=context.run_job_ids,
            ),
        )
        return IntentEvalExecution(intent=intent)


@dataclass(frozen=True, slots=True)
class IntentEvalCaseResult:
    case_id: str
    passed: bool
    failure_reasons: tuple[str, ...]
    provider_attempts: int
    provider_completed: int
    business_writes: int


@dataclass(frozen=True, slots=True)
class IntentEvalReport:
    total_cases: int
    passed_cases: int
    failed_cases: int
    gate_passed: bool
    case_results: tuple[IntentEvalCaseResult, ...]


def load_career_intent_eval_dataset(
    path: str | Path = _DEFAULT_DATASET_PATH,
) -> tuple[IntentEvalCase, ...]:
    """Load a versioned JSONL cohort and enforce frozen release minimums."""

    dataset_path = Path(path)
    cases: list[IntentEvalCase] = []
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
                f"invalid CareerIntent Eval JSONL at line {line_number}"
            ) from exc
        case = _parse_case(payload, line_number=line_number)
        if case.case_id in case_ids:
            raise ValueError(f"duplicate CareerIntent Eval case id: {case.case_id}")
        case_ids.add(case.case_id)
        cases.append(case)

    validate_career_intent_release_dataset(tuple(cases))
    return tuple(cases)


def validate_career_intent_release_dataset(
    cases: tuple[IntentEvalCase, ...],
) -> None:
    """Prevent a smaller or category-skewed dataset from claiming the gate."""

    if len(cases) < _RELEASE_MINIMUM_TOTAL:
        raise ValueError(
            f"CareerIntent Eval requires at least {_RELEASE_MINIMUM_TOTAL} cases"
        )

    duplicate_ids = [case_id for case_id, count in Counter(case.case_id for case in cases).items() if count > 1]
    if duplicate_ids:
        raise ValueError(
            "duplicate CareerIntent Eval case ids: " + ", ".join(sorted(duplicate_ids))
        )

    category_counts = Counter(case.category for case in cases)
    missing = [
        f"{category.value} >= {minimum} (got {category_counts[category]})"
        for category, minimum in _RELEASE_MINIMUMS.items()
        if category_counts[category] < minimum
    ]
    if missing:
        raise ValueError("CareerIntent Eval dataset category minimums failed: " + "; ".join(missing))


def evaluate_career_intents(
    *,
    router: IntentEvalRouter,
    cases: tuple[IntentEvalCase, ...],
    require_release_dataset: bool = True,
) -> IntentEvalReport:
    """Evaluate an injected router with exact goals and fail-closed guardrails."""

    if not cases:
        raise ValueError("CareerIntent Eval requires at least one case")
    if require_release_dataset:
        validate_career_intent_release_dataset(cases)

    results = tuple(_evaluate_case(router=router, case=case) for case in cases)
    passed_cases = sum(result.passed for result in results)
    return IntentEvalReport(
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=len(results) - passed_cases,
        gate_passed=passed_cases == len(results),
        case_results=results,
    )


def _parse_case(payload: object, *, line_number: int) -> IntentEvalCase:
    if not isinstance(payload, dict):
        raise ValueError(f"CareerIntent Eval line {line_number} must be an object")

    case_id = _required_string(payload, "id", line_number=line_number)
    category_raw = _required_string(payload, "category", line_number=line_number)
    try:
        category = IntentEvalCategory(category_raw)
    except ValueError as exc:
        allowed = ", ".join(category.value for category in IntentEvalCategory)
        raise ValueError(
            f"CareerIntent Eval line {line_number} has invalid category {category_raw!r}; expected one of {allowed}"
        ) from exc

    message = _required_string(payload, "message", line_number=line_number)
    context_payload = _object(payload.get("context", {}), field="context", line_number=line_number)
    expected_payload = _object(payload.get("expected"), field="expected", line_number=line_number)
    context = IntentEvalContext(
        current_job_id=_optional_string(
            context_payload.get("currentJobId"),
            field="context.currentJobId",
            line_number=line_number,
        ),
        run_job_ids=_string_tuple(
            context_payload.get("runJobIds", []),
            field="context.runJobIds",
            line_number=line_number,
        ),
    )
    expected = IntentEvalExpected(
        goals=_string_tuple(
            expected_payload.get("goals"),
            field="expected.goals",
            line_number=line_number,
        ),
        referenced_job_ids=_string_tuple(
            expected_payload.get("referencedJobIds", []),
            field="expected.referencedJobIds",
            line_number=line_number,
        ),
        current_job_required=_required_bool(
            expected_payload,
            "currentJobRequired",
            line_number=line_number,
        ),
        needs_clarification=_required_bool(
            expected_payload,
            "needsClarification",
            line_number=line_number,
        ),
        clarification_question_contains=_optional_string(
            expected_payload.get("clarificationQuestionContains"),
            field="expected.clarificationQuestionContains",
            line_number=line_number,
        ),
        unsupported_request=_optional_string(
            expected_payload.get("unsupportedRequest"),
            field="expected.unsupportedRequest",
            line_number=line_number,
        ),
    )
    _validate_case_semantics(case_id=case_id, category=category, context=context, expected=expected)
    return IntentEvalCase(
        case_id=case_id,
        category=category,
        message=message,
        context=context,
        expected=expected,
    )


def _validate_case_semantics(
    *,
    case_id: str,
    category: IntentEvalCategory,
    context: IntentEvalContext,
    expected: IntentEvalExpected,
) -> None:
    if category is IntentEvalCategory.MULTI_GOAL and len(expected.goals) < 2:
        raise ValueError(f"{case_id}: multi_goal case requires at least two ordered goals")
    if category is IntentEvalCategory.UNSUPPORTED_UNSAFE:
        if expected.goals or not expected.unsupported_request:
            raise ValueError(
                f"{case_id}: unsupported_unsafe case requires no goals and an unsupportedRequest"
            )
    if expected.needs_clarification and any(
        goal != CareerIntentGoal.UNKNOWN.value for goal in expected.goals
    ):
        raise ValueError(
            f"{case_id}: clarification cannot expect executable goals"
        )
    if category is IntentEvalCategory.CLARIFICATION:
        if not expected.needs_clarification:
            raise ValueError(f"{case_id}: clarification case requires needsClarification")
        if not expected.clarification_question_contains:
            raise ValueError(
                f"{case_id}: clarification case must state clarificationQuestionContains"
            )
    if not expected.needs_clarification and expected.clarification_question_contains:
        raise ValueError(
            f"{case_id}: clarificationQuestionContains requires needsClarification"
        )
    if context.run_job_ids and any(
        job_id not in context.run_job_ids for job_id in expected.referenced_job_ids
    ):
        raise ValueError(f"{case_id}: expected referenced job is outside runJobIds")
    if (
        expected.current_job_required
        and context.current_job_id is None
        and expected.referenced_job_ids
    ):
        raise ValueError(
            f"{case_id}: missing current job must not expect a guessed referenced job"
        )


def _evaluate_case(*, router: IntentEvalRouter, case: IntentEvalCase) -> IntentEvalCaseResult:
    failure_reasons: list[str] = []
    try:
        execution = router.route(message=case.message, context=case.context)
    except Exception as exc:  # Core router failures must be represented per case.
        return IntentEvalCaseResult(
            case_id=case.case_id,
            passed=False,
            failure_reasons=(f"router raised {type(exc).__name__}: {exc}",),
            provider_attempts=0,
            provider_completed=0,
            business_writes=0,
        )

    _assert_safety_budgets(execution=execution, failures=failure_reasons)
    _assert_intent_shape_and_expectations(
        intent=execution.intent,
        case=case,
        failures=failure_reasons,
    )
    return IntentEvalCaseResult(
        case_id=case.case_id,
        passed=not failure_reasons,
        failure_reasons=tuple(failure_reasons),
        provider_attempts=execution.provider_attempts,
        provider_completed=execution.provider_completed,
        business_writes=execution.business_writes,
    )


def _assert_safety_budgets(*, execution: IntentEvalExecution, failures: list[str]) -> None:
    for field_name, actual in (
        ("provider attempts", execution.provider_attempts),
        ("provider completed", execution.provider_completed),
        ("business writes", execution.business_writes),
    ):
        if actual != 0:
            failures.append(f"{field_name} must be 0 during deterministic Intent Eval, got {actual}")


def _assert_intent_shape_and_expectations(
    *,
    intent: object,
    case: IntentEvalCase,
    failures: list[str],
) -> None:
    actual_goals = _intent_string_tuple(intent, "goals", failures)
    actual_references = _intent_string_tuple(intent, "referenced_job_ids", failures)
    actual_current_job_required = _intent_bool(intent, "current_job_required", failures)
    actual_needs_clarification = _intent_bool(intent, "needs_clarification", failures)
    actual_question = _intent_optional_string(intent, "clarification_question", failures)
    actual_unsupported = _intent_optional_string(intent, "unsupported_request", failures)

    expected = case.expected
    if actual_goals != expected.goals:
        failures.append(f"goals expected {expected.goals!r}, got {actual_goals!r}")
    if actual_references != expected.referenced_job_ids:
        failures.append(
            "referenced_job_ids expected "
            f"{expected.referenced_job_ids!r}, got {actual_references!r}"
        )
    if actual_current_job_required != expected.current_job_required:
        failures.append(
            "current_job_required expected "
            f"{expected.current_job_required!r}, got {actual_current_job_required!r}"
        )
    if actual_needs_clarification != expected.needs_clarification:
        failures.append(
            "needs_clarification expected "
            f"{expected.needs_clarification!r}, got {actual_needs_clarification!r}"
        )
    if actual_unsupported != expected.unsupported_request:
        failures.append(
            "unsupported_request expected "
            f"{expected.unsupported_request!r}, got {actual_unsupported!r}"
        )
    if actual_needs_clarification and not actual_question:
        failures.append(
            "clarification must carry a non-empty clarification_question"
        )
    if expected.clarification_question_contains and (
        actual_question is None
        or expected.clarification_question_contains.casefold() not in actual_question.casefold()
    ):
        failures.append(
            "clarification_question must contain "
            f"{expected.clarification_question_contains!r}, got {actual_question!r}"
        )
    if actual_needs_clarification and any(
        goal != CareerIntentGoal.UNKNOWN.value for goal in actual_goals
    ):
        failures.append("clarification must not carry executable goals")

    if case.context.run_job_ids and any(
        job_id not in case.context.run_job_ids for job_id in actual_references
    ):
        failures.append("referenced_job_ids contain a job outside the governed run scope")
    if (
        expected.current_job_required
        and case.context.current_job_id is None
        and actual_references
    ):
        failures.append("missing current job must not resolve or guess a referenced job")
    if expected.unsupported_request and actual_goals:
        failures.append("unsupported request must not carry executable goals")


def _intent_string_tuple(intent: object, field: str, failures: list[str]) -> tuple[str, ...]:
    value = _intent_field(intent, field, failures)
    if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
        failures.append(f"intent.{field} must be tuple[str, ...]")
        return ()
    return value


def _intent_bool(intent: object, field: str, failures: list[str]) -> bool:
    value = _intent_field(intent, field, failures)
    if not isinstance(value, bool):
        failures.append(f"intent.{field} must be bool")
        return False
    return value


def _intent_optional_string(intent: object, field: str, failures: list[str]) -> str | None:
    value = _intent_field(intent, field, failures)
    if value is not None and not isinstance(value, str):
        failures.append(f"intent.{field} must be str | None")
        return None
    return value


def _intent_field(intent: object, field: str, failures: list[str]) -> object:
    if not hasattr(intent, field):
        failures.append(f"intent is missing required field {field!r}")
        return None
    return getattr(intent, field)


def _required_string(payload: dict[str, object], field: str, *, line_number: int) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"CareerIntent Eval line {line_number} requires non-empty {field}")
    return value


def _optional_string(value: object, *, field: str, line_number: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"CareerIntent Eval line {line_number} field {field} must be non-empty str | null")
    return value


def _object(value: object, *, field: str, line_number: int) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"CareerIntent Eval line {line_number} field {field} must be an object")
    return value


def _string_tuple(value: object, *, field: str, line_number: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"CareerIntent Eval line {line_number} field {field} must be string array")
    return tuple(value)


def _required_bool(payload: dict[str, object], field: str, *, line_number: int) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"CareerIntent Eval line {line_number} field {field} must be bool")
    return value


__all__ = [
    "CareerIntentCoreEvalAdapter",
    "IntentEvalCase",
    "IntentEvalCaseResult",
    "IntentEvalCategory",
    "IntentEvalContext",
    "IntentEvalExecution",
    "IntentEvalExpected",
    "IntentEvalReport",
    "IntentEvalRouter",
    "evaluate_career_intents",
    "load_career_intent_eval_dataset",
    "validate_career_intent_release_dataset",
]
