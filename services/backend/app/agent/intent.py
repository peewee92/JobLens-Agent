"""Governed natural-language intent contract for Career Agent vNext 1.1.

This module deliberately does not call an LLM.  It defines the framework- and
provider-independent boundary that a later intent model must satisfy, and it
resolves only job references that are already grounded in governed context.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CareerIntentGoal(StrEnum):
    RANK_JOBS = "rank_jobs"
    REVIEW_GAPS = "review_gaps"
    PREPARE_JOB = "prepare_job"
    REVIEW_APPLICATION = "review_application"
    UNKNOWN = "unknown"


class CareerIntentValidationError(ValueError):
    """Raised when an intent would cross a governed execution boundary."""


@dataclass(frozen=True, slots=True)
class CareerIntent:
    """Structured, auditable output expected from future intent understanding."""

    goals: tuple[CareerIntentGoal, ...] = ()
    referenced_job_ids: tuple[str, ...] = ()
    current_job_required: bool = False
    needs_clarification: bool = False
    clarification_question: str | None = None
    unsupported_request: str | None = None
    confidence: float | None = None
    reasoning_summary: str = ""

    def __post_init__(self) -> None:
        if self.unsupported_request and any(
            goal not in (CareerIntentGoal.UNKNOWN,) for goal in self.goals
        ):
            raise CareerIntentValidationError(
                "unsupported request cannot carry executable goals"
            )
        if self.needs_clarification and not self.clarification_question:
            raise CareerIntentValidationError(
                "needs_clarification requires clarification_question"
            )
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise CareerIntentValidationError("confidence must be between 0 and 1")
        if len(self.reasoning_summary) > 500:
            raise CareerIntentValidationError(
                "reasoning_summary must be bounded audit text (<= 500 chars)"
            )


@dataclass(frozen=True, slots=True)
class CareerIntentResolutionContext:
    """Only references already authorized for the current turn/run."""

    current_job_id: str | None = None
    run_job_ids: tuple[str, ...] = ()


class CareerIntentResolver:
    """Ground job references without title guessing or widening run scope."""

    def resolve(
        self,
        *,
        intent: CareerIntent,
        context: CareerIntentResolutionContext,
    ) -> CareerIntent:
        run_scope = set(context.run_job_ids)
        referenced = list(dict.fromkeys(intent.referenced_job_ids))

        if run_scope:
            outside_scope = [job_id for job_id in referenced if job_id not in run_scope]
            if outside_scope:
                raise CareerIntentValidationError(
                    "referenced job is outside the governed run scope"
                )

        if intent.current_job_required and not referenced:
            current_job_id = context.current_job_id
            if current_job_id is None:
                return CareerIntent(
                    goals=intent.goals,
                    referenced_job_ids=(),
                    current_job_required=True,
                    needs_clarification=True,
                    clarification_question="请先明确你指的是哪个岗位。",
                    unsupported_request=intent.unsupported_request,
                    confidence=intent.confidence,
                    reasoning_summary=intent.reasoning_summary,
                )
            if run_scope and current_job_id not in run_scope:
                raise CareerIntentValidationError(
                    "current job is outside the governed run scope"
                )
            referenced.append(current_job_id)

        return CareerIntent(
            goals=intent.goals,
            referenced_job_ids=tuple(referenced),
            current_job_required=intent.current_job_required,
            needs_clarification=intent.needs_clarification,
            clarification_question=intent.clarification_question,
            unsupported_request=intent.unsupported_request,
            confidence=intent.confidence,
            reasoning_summary=intent.reasoning_summary,
        )


__all__ = [
    "CareerIntent",
    "CareerIntentGoal",
    "CareerIntentResolutionContext",
    "CareerIntentResolver",
    "CareerIntentValidationError",
]
