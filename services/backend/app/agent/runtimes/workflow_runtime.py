"""Workflow-backed Career Agent runtime adapter.

This adapter preserves the existing deterministic single-turn Career Agent
behavior while moving callers behind the framework-neutral runtime boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.agent.entrypoint import CareerAgentTurn, CareerAgentTurnResult


class CareerAgentTurnEntrypoint(Protocol):
    def execute(self, turn: CareerAgentTurn) -> CareerAgentTurnResult: ...


@dataclass(slots=True)
class WorkflowCareerAgentRuntime:
    """Delegate a runtime turn to the existing governed workflow entrypoint."""

    entrypoint: CareerAgentTurnEntrypoint

    def run(self, request: CareerAgentTurn) -> CareerAgentTurnResult:
        return self.entrypoint.execute(request)


__all__ = ["WorkflowCareerAgentRuntime"]
