"""Framework-neutral Career Agent runtime boundary.

LG-0 intentionally defines only the stable single-turn execution seam. Durable
lifecycle operations such as checkpoint state, resume, and cancel are added by
LG-1/LG-2 once their state contracts exist rather than being faked with empty
stubs here.
"""
from __future__ import annotations

from typing import Protocol

from app.agent.entrypoint import CareerAgentTurn, CareerAgentTurnResult


class CareerAgentRuntime(Protocol):
    """Execute a governed Career Agent turn without exposing runtime framework types."""

    def run(self, request: CareerAgentTurn) -> CareerAgentTurnResult: ...


__all__ = ["CareerAgentRuntime"]
