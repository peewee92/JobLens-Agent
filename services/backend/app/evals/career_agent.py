"""Deterministic Career Agent orchestration Eval.

This gate evaluates the governed structured entrypoint without any live Provider
calls. It measures routing, fail-closed behavior, and grounding-reference
preservation. It does not claim natural-language routing quality.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.agent.entrypoint import (
    CareerAgentEntrypointError,
    CareerAgentTurn,
    CareerAgentTurnResult,
)
from app.agent.tool_registry import CareerAgentToolName


class CareerAgentTurnExecutor(Protocol):
    def execute(self, turn: CareerAgentTurn) -> CareerAgentTurnResult: ...


@dataclass(frozen=True, slots=True)
class CareerAgentEvalCase:
    case_id: str
    turn: CareerAgentTurn
    expected_tool: CareerAgentToolName | None
    expect_error: bool = False
    required_grounding_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CareerAgentEvalCaseResult:
    case_id: str
    passed: bool
    actual_tool: CareerAgentToolName | None
    error: str | None
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CareerAgentEvalReport:
    total_cases: int
    passed_cases: int
    failed_cases: int
    gate_passed: bool
    case_results: tuple[CareerAgentEvalCaseResult, ...]


def evaluate_career_agent(
    *,
    entrypoint: CareerAgentTurnExecutor,
    cases: tuple[CareerAgentEvalCase, ...],
) -> CareerAgentEvalReport:
    """Run deterministic orchestration cases and return a strict all-cases gate."""

    if not cases:
        raise ValueError("Career Agent Eval requires at least one case")

    results = tuple(_evaluate_case(entrypoint=entrypoint, case=case) for case in cases)
    passed_cases = sum(result.passed for result in results)
    return CareerAgentEvalReport(
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=len(results) - passed_cases,
        gate_passed=passed_cases == len(results),
        case_results=results,
    )


def _evaluate_case(
    *,
    entrypoint: CareerAgentTurnExecutor,
    case: CareerAgentEvalCase,
) -> CareerAgentEvalCaseResult:
    failure_reasons: list[str] = []
    actual_tool: CareerAgentToolName | None = None
    error: str | None = None

    try:
        result = entrypoint.execute(case.turn)
        actual_tool = result.tool
    except CareerAgentEntrypointError as exc:
        error = str(exc)
        result = None

    if case.expect_error:
        if error is None:
            failure_reasons.append("expected fail-closed error but turn completed")
    elif error is not None:
        failure_reasons.append(f"unexpected entrypoint error: {error}")

    if actual_tool is not case.expected_tool:
        expected = case.expected_tool.value if case.expected_tool is not None else None
        actual = actual_tool.value if actual_tool is not None else None
        failure_reasons.append(f"expected tool {expected!r}, got {actual!r}")

    if case.required_grounding_keys and result is not None:
        available_keys = _collect_mapping_keys(result.output)
        missing = tuple(
            key for key in case.required_grounding_keys if key not in available_keys
        )
        if missing:
            failure_reasons.append(
                "missing grounding references: " + ", ".join(missing)
            )

    return CareerAgentEvalCaseResult(
        case_id=case.case_id,
        passed=not failure_reasons,
        actual_tool=actual_tool,
        error=error,
        failure_reasons=tuple(failure_reasons),
    )


def _collect_mapping_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str):
                keys.add(key)
            keys.update(_collect_mapping_keys(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            keys.update(_collect_mapping_keys(nested))
    return keys


__all__ = [
    "CareerAgentEvalCase",
    "CareerAgentEvalCaseResult",
    "CareerAgentEvalReport",
    "evaluate_career_agent",
]
