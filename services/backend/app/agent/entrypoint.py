"""Single governed Career Agent entrypoint.

This is intentionally a structured single-turn orchestration boundary. It does
not interpret free-form language yet: callers choose one approved goal and
supply the explicit IDs required by the mature workflow. That keeps the first
user-facing Agent entry deterministic and testable before adding an LLM intent
router in Agent Eval.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.agent.context import CareerAgentContext, CareerAgentContextBuilder
from app.agent.tool_registry import (
    CareerAgentToolName,
    CareerAgentToolRegistry,
    JobPreparationRequest,
    RankMatchReportsRequest,
    TargetCohortGapsRequest,
)


class CareerAgentGoal(StrEnum):
    RANK_JOBS = "rank_jobs"
    REVIEW_GAPS = "review_gaps"
    PREPARE_JOB = "prepare_job"


@dataclass(frozen=True, slots=True)
class CareerAgentTurn:
    goal: CareerAgentGoal
    current_job_id: str | None = None
    relevant_evidence_ids: tuple[str, ...] = ()
    job_ids: tuple[str, ...] = ()
    include_blocked: bool = False
    top_n: int | None = None
    cohort_id: str | None = None
    cohort_name: str | None = None
    selected_feedback_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CareerAgentTurnResult:
    context: CareerAgentContext
    goal: CareerAgentGoal
    tool: CareerAgentToolName | None
    output: object | None


class CareerAgentEntrypointError(ValueError):
    """Raised when a structured turn is incomplete before workflow execution."""


class CareerAgentEntrypoint:
    """Build governed context then delegate one explicit goal to the registry."""

    def __init__(
        self,
        *,
        context_builder: CareerAgentContextBuilder,
        tools: CareerAgentToolRegistry,
    ) -> None:
        self._context_builder = context_builder
        self._tools = tools

    def execute(self, turn: CareerAgentTurn) -> CareerAgentTurnResult:
        context = self._context_builder.build(
            current_job_id=turn.current_job_id,
            relevant_evidence_ids=turn.relevant_evidence_ids,
        )
        if not context.usable:
            return CareerAgentTurnResult(
                context=context,
                goal=turn.goal,
                tool=None,
                output=None,
            )

        if turn.goal is CareerAgentGoal.RANK_JOBS:
            if not turn.job_ids:
                raise CareerAgentEntrypointError("rank_jobs requires explicit job_ids")
            tool = CareerAgentToolName.RANK_MATCH_REPORTS
            output = self._tools.invoke(
                context=context,
                tool=tool,
                request=RankMatchReportsRequest(
                    job_ids=turn.job_ids,
                    include_blocked=turn.include_blocked,
                    top_n=turn.top_n,
                ),
            )
        elif turn.goal is CareerAgentGoal.REVIEW_GAPS:
            if not turn.cohort_id or not turn.cohort_name:
                raise CareerAgentEntrypointError(
                    "review_gaps requires cohort_id and cohort_name"
                )
            if not turn.selected_feedback_ids:
                raise CareerAgentEntrypointError(
                    "review_gaps requires explicit selected_feedback_ids"
                )
            tool = CareerAgentToolName.TARGET_COHORT_GAPS
            output = self._tools.invoke(
                context=context,
                tool=tool,
                request=TargetCohortGapsRequest(
                    cohort_id=turn.cohort_id,
                    name=turn.cohort_name,
                    selected_feedback_ids=turn.selected_feedback_ids,
                ),
            )
        elif turn.goal is CareerAgentGoal.PREPARE_JOB:
            if context.current_job is None:
                raise CareerAgentEntrypointError(
                    "prepare_job requires an explicitly governed current_job_id"
                )
            tool = CareerAgentToolName.JOB_PREPARATION
            output = self._tools.invoke(
                context=context,
                tool=tool,
                request=JobPreparationRequest(job_id=context.current_job.id),
            )
        else:  # pragma: no cover - StrEnum exhaustiveness guard
            raise CareerAgentEntrypointError(f"unsupported Career Agent goal: {turn.goal}")

        return CareerAgentTurnResult(
            context=context,
            goal=turn.goal,
            tool=tool,
            output=output,
        )


__all__ = [
    "CareerAgentEntrypoint",
    "CareerAgentEntrypointError",
    "CareerAgentGoal",
    "CareerAgentTurn",
    "CareerAgentTurnResult",
]
