"""Durable target-cohort human decision boundary for LG-2.

This slice consumes an already-persisted interrupt exactly once. It validates
only the explicit human decision and advances runtime state to RESUMING (or
CANCELLED for reject). Stale-domain validation and downstream Skill Gap resume
remain separate LG-2 steps so no business workflow is executed prematurely.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.state import CareerAgentState, CareerAgentStatus


HumanDecision = Literal["approve", "edit", "reject"]


@dataclass(frozen=True, slots=True)
class HumanDecisionRequest:
    thread_id: str
    interrupt_id: str
    action_id: str
    decision: HumanDecision
    selected_job_ids: tuple[str, ...] = ()


class HumanDecisionError(ValueError):
    """Base error for durable human-decision contract failures."""


class HumanDecisionValidationError(HumanDecisionError):
    """Raised when a decision cannot safely consume the pending interrupt."""


class HumanDecisionConflictError(HumanDecisionError):
    """Raised when a completed decision is followed by a different action."""


class TargetCohortDecisionHandler:
    """Consume the first durable Target Cohort interrupt idempotently."""

    def __init__(self, *, checkpoints: SQLiteCareerAgentCheckpointStore) -> None:
        self._checkpoints = checkpoints

    def submit(self, request: HumanDecisionRequest) -> CareerAgentState:
        if not request.action_id.strip():
            raise HumanDecisionValidationError("action_id is required")
        state = self._checkpoints.load(thread_id=request.thread_id)
        if state is None:
            raise HumanDecisionValidationError("career agent thread does not exist")

        if state.decision_action_id is not None:
            if state.decision_action_id == request.action_id:
                return state
            raise HumanDecisionConflictError("target cohort interrupt was already consumed")

        if state.status is not CareerAgentStatus.INTERRUPTED or not state.pending_approval:
            raise HumanDecisionValidationError("career agent thread is not awaiting a decision")
        if state.current_step != "target_cohort_confirmation":
            raise HumanDecisionValidationError("unexpected pending Career Agent step")
        if state.interrupt_id != request.interrupt_id:
            raise HumanDecisionValidationError("interrupt_id does not match pending interrupt")

        if request.decision == "reject":
            result = replace(
                state,
                status=CareerAgentStatus.CANCELLED,
                current_step="target_cohort_rejected",
                pending_approval=False,
                human_decision="reject",
                decision_action_id=request.action_id,
                confirmed_target_job_ids=(),
            )
            self._checkpoints.save(result)
            return result

        if request.decision == "approve":
            selected_job_ids = state.proposed_target_job_ids
        elif request.decision == "edit":
            selected_job_ids = tuple(dict.fromkeys(request.selected_job_ids))
            if not 1 <= len(selected_job_ids) <= 10:
                raise HumanDecisionValidationError("edit selection must contain 1..10 jobs")
            requested_scope = set(state.requested_job_ids)
            if any(job_id not in requested_scope for job_id in selected_job_ids):
                raise HumanDecisionValidationError("edit selection contains a job outside run scope")
        else:
            raise HumanDecisionValidationError("decision must be approve, edit, or reject")

        if not selected_job_ids:
            raise HumanDecisionValidationError("target cohort selection cannot be empty")

        result = replace(
            state,
            status=CareerAgentStatus.RESUMING,
            current_step="target_cohort_resume",
            pending_approval=False,
            human_decision=request.decision,
            decision_action_id=request.action_id,
            confirmed_target_job_ids=selected_job_ids,
        )
        self._checkpoints.save(result)
        return result


__all__ = [
    "HumanDecisionConflictError",
    "HumanDecisionError",
    "HumanDecisionRequest",
    "HumanDecisionValidationError",
    "TargetCohortDecisionHandler",
]
