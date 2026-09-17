"""Governed Career Agent registry for mature read-only workflows.

The registry exposes coarse-grained application workflows, not low-level business
rules. Anything that can spend Provider budget, write user decisions, or persist
Match state is deliberately absent until a later explicit confirmation boundary is
designed for the unified Agent entrypoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.agent.context import CareerAgentContext
from app.application.create_target_cohort import (
    CreateFeedbackTargetCohortCommand,
    CreateManualTargetCohortCommand,
)


class CareerAgentToolName(StrEnum):
    RANK_MATCH_REPORTS = "rank_match_reports"
    TARGET_COHORT_GAPS = "target_cohort_gaps"
    JOB_PREPARATION = "job_preparation"


class CareerAgentToolAccess(StrEnum):
    READ_ONLY = "read_only"


@dataclass(frozen=True, slots=True)
class CareerAgentToolDefinition:
    name: CareerAgentToolName
    description: str
    access: CareerAgentToolAccess
    requires_current_job: bool = False
    requires_explicit_feedback_selection: bool = False


@dataclass(frozen=True, slots=True)
class RankMatchReportsRequest:
    job_ids: tuple[str, ...]
    include_blocked: bool = False
    top_n: int | None = None


@dataclass(frozen=True, slots=True)
class TargetCohortGapsRequest:
    cohort_id: str
    name: str
    selected_feedback_ids: tuple[str, ...] = ()
    selected_job_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class JobPreparationRequest:
    job_id: str | None = None


CareerAgentToolRequest = (
    RankMatchReportsRequest | TargetCohortGapsRequest | JobPreparationRequest
)


class RankMatchReportsWorkflow(Protocol):
    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        include_blocked: bool = False,
        top_n: int | None = None,
    ) -> object: ...


class TargetCohortGapsWorkflow(Protocol):
    def execute(self, command: CreateFeedbackTargetCohortCommand) -> object: ...


class JobPreparationWorkflow(Protocol):
    def execute(self, job_id: str) -> object: ...


class CareerAgentToolError(ValueError):
    """Raised before workflow execution when an Agent tool request is not governed."""


class CareerAgentToolRegistry:
    """Delegate approved Agent calls to existing mature application workflows."""

    _DEFINITIONS = (
        CareerAgentToolDefinition(
            name=CareerAgentToolName.RANK_MATCH_REPORTS,
            description="Read current immutable MatchReports through the existing Ranking workflow.",
            access=CareerAgentToolAccess.READ_ONLY,
        ),
        CareerAgentToolDefinition(
            name=CareerAgentToolName.TARGET_COHORT_GAPS,
            description="Build grounded Skill Gap and Action Plan facts from explicitly selected current UserFeedback.",
            access=CareerAgentToolAccess.READ_ONLY,
            requires_explicit_feedback_selection=True,
        ),
        CareerAgentToolDefinition(
            name=CareerAgentToolName.JOB_PREPARATION,
            description="Read the existing grounded Resume/Story/Interview/Study preparation bundle for the current Job.",
            access=CareerAgentToolAccess.READ_ONLY,
            requires_current_job=True,
        ),
    )

    def __init__(
        self,
        *,
        ranking: RankMatchReportsWorkflow,
        target_cohort_gaps: TargetCohortGapsWorkflow,
        job_preparation: JobPreparationWorkflow,
    ) -> None:
        self._ranking = ranking
        self._target_cohort_gaps = target_cohort_gaps
        self._job_preparation = job_preparation

    def definitions(self) -> tuple[CareerAgentToolDefinition, ...]:
        return self._DEFINITIONS

    def invoke(
        self,
        *,
        context: CareerAgentContext,
        tool: CareerAgentToolName,
        request: CareerAgentToolRequest,
    ) -> object:
        if not context.usable:
            raise CareerAgentToolError("Agent context must be usable before invoking a workflow")

        if tool is CareerAgentToolName.RANK_MATCH_REPORTS:
            if not isinstance(request, RankMatchReportsRequest):
                raise CareerAgentToolError("rank_match_reports requires RankMatchReportsRequest")
            if not request.job_ids:
                raise CareerAgentToolError("rank_match_reports requires at least one explicit Job ID")
            return self._ranking.execute(
                tuple(dict.fromkeys(request.job_ids)),
                include_blocked=request.include_blocked,
                top_n=request.top_n,
            )

        if tool is CareerAgentToolName.TARGET_COHORT_GAPS:
            if not isinstance(request, TargetCohortGapsRequest):
                raise CareerAgentToolError("target_cohort_gaps requires TargetCohortGapsRequest")
            selected_feedback_ids = tuple(dict.fromkeys(request.selected_feedback_ids))
            selected_job_ids = tuple(dict.fromkeys(request.selected_job_ids))
            if not selected_feedback_ids and not selected_job_ids:
                raise CareerAgentToolError(
                    "target_cohort_gaps requires explicit current UserFeedback or Job selection"
                )
            if selected_feedback_ids and selected_job_ids:
                raise CareerAgentToolError(
                    "target_cohort_gaps accepts exactly one explicit feedback or Job selection"
                )
            if selected_job_ids:
                return self._target_cohort_gaps.execute(
                    CreateManualTargetCohortCommand(
                        cohort_id=request.cohort_id,
                        name=request.name,
                        selected_job_ids=selected_job_ids,
                    )
                )
            return self._target_cohort_gaps.execute(
                CreateFeedbackTargetCohortCommand(
                    cohort_id=request.cohort_id,
                    name=request.name,
                    selected_feedback_ids=selected_feedback_ids,
                )
            )

        if tool is CareerAgentToolName.JOB_PREPARATION:
            if not isinstance(request, JobPreparationRequest):
                raise CareerAgentToolError("job_preparation requires JobPreparationRequest")
            job_id = request.job_id
            if context.current_job is None:
                raise CareerAgentToolError(
                    "job_preparation requires an explicitly governed current Job"
                )
            if job_id is not None and job_id != context.current_job.id:
                raise CareerAgentToolError(
                    "job_preparation cannot switch away from the governed current Job"
                )
            return self._job_preparation.execute(context.current_job.id)

        raise CareerAgentToolError(f"unregistered Career Agent tool: {tool}")


__all__ = [
    "CareerAgentToolAccess",
    "CareerAgentToolDefinition",
    "CareerAgentToolError",
    "CareerAgentToolName",
    "CareerAgentToolRegistry",
    "JobPreparationRequest",
    "RankMatchReportsRequest",
    "TargetCohortGapsRequest",
]
