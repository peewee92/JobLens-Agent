"""Governed intent-to-tool selection for Career Agent vNext 1.1.

Selection is deliberately separate from invocation.  It may choose only tools
already registered as mature workflows; argument construction and bounded loop
execution remain later vNext 1.1 boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agent.intent import CareerIntent, CareerIntentGoal
from app.agent.tool_registry import (
    CareerAgentToolDefinition,
    CareerAgentToolError,
    CareerAgentToolName,
    CareerAgentToolRegistry,
)


class CareerAgentToolSelectionError(ValueError):
    """Raised when an intent cannot map to an approved registered workflow."""


@dataclass(frozen=True, slots=True)
class CareerAgentToolSelection:
    goal: CareerIntentGoal
    tool: CareerAgentToolDefinition


class CareerAgentToolSelector:
    """Map governed intent goals to coarse-grained registered workflows."""

    _GOAL_TO_TOOL = {
        CareerIntentGoal.RANK_JOBS: CareerAgentToolName.RANK_MATCH_REPORTS,
        CareerIntentGoal.REVIEW_GAPS: CareerAgentToolName.TARGET_COHORT_GAPS,
        CareerIntentGoal.PREPARE_JOB: CareerAgentToolName.JOB_PREPARATION,
    }

    def __init__(self, *, registry: CareerAgentToolRegistry) -> None:
        self._registry = registry

    def select(self, intent: CareerIntent) -> tuple[CareerAgentToolSelection, ...]:
        if intent.needs_clarification or intent.unsupported_request:
            return ()

        selections: list[CareerAgentToolSelection] = []
        for goal in intent.goals:
            tool_name = self._GOAL_TO_TOOL.get(goal)
            if tool_name is None:
                raise CareerAgentToolSelectionError(
                    f"no registered tool for Career Agent goal: {goal.value}"
                )
            try:
                definition = self._registry.definition(tool_name)
            except CareerAgentToolError as exc:
                raise CareerAgentToolSelectionError(
                    f"registered tool unavailable for Career Agent goal: {goal.value}"
                ) from exc
            selections.append(CareerAgentToolSelection(goal=goal, tool=definition))
        return tuple(selections)


__all__ = [
    "CareerAgentToolSelection",
    "CareerAgentToolSelectionError",
    "CareerAgentToolSelector",
]
