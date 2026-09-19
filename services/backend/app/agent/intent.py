"""Governed natural-language intent contract for Career Agent vNext 1.1.

This module deliberately does not call an LLM.  It defines the framework- and
provider-independent boundary that a later intent model must satisfy, and it
resolves only job references that are already grounded in governed context.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class CareerIntentGoal(StrEnum):
    RANK_JOBS = "rank_jobs"
    REVIEW_GAPS = "review_gaps"
    PREPARE_JOB = "prepare_job"
    REVIEW_APPLICATION = "review_application"
    UNKNOWN = "unknown"


class CareerIntentValidationError(ValueError):
    """Raised when an intent would cross a governed execution boundary."""


class CareerIntentModel(Protocol):
    """Provider-independent seam for structured natural-language routing."""

    def route(self, user_message: str) -> dict[str, object]: ...


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
        if self.needs_clarification and any(
            goal not in (CareerIntentGoal.UNKNOWN,) for goal in self.goals
        ):
            raise CareerIntentValidationError(
                "clarification cannot carry executable goals"
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


class CareerIntentRouter:
    """Convert model output into the governed intent contract, then ground it."""

    _FIELDS = frozenset(
        {
            "goals",
            "referenced_job_ids",
            "current_job_required",
            "needs_clarification",
            "clarification_question",
            "unsupported_request",
            "confidence",
            "reasoning_summary",
        }
    )

    def __init__(
        self,
        *,
        model: CareerIntentModel,
        resolver: CareerIntentResolver | None = None,
    ) -> None:
        self._model = model
        self._resolver = resolver or CareerIntentResolver()

    def route(
        self,
        *,
        user_message: str,
        context: CareerIntentResolutionContext,
    ) -> CareerIntent:
        if not user_message.strip():
            raise CareerIntentValidationError("user message must not be empty")
        payload = self._model.route(user_message)
        try:
            intent = self._parse(payload)
        except CareerIntentValidationError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise CareerIntentValidationError("invalid intent model output") from exc
        return self._resolver.resolve(intent=intent, context=context)

    def _parse(self, payload: dict[str, object]) -> CareerIntent:
        if not isinstance(payload, dict) or set(payload) - self._FIELDS:
            raise ValueError("unexpected intent fields")
        goals_value = payload.get("goals", [])
        referenced_value = payload.get("referenced_job_ids", [])
        if not isinstance(goals_value, list) or not all(
            isinstance(value, str) for value in goals_value
        ):
            raise TypeError("goals must be a string list")
        if not isinstance(referenced_value, list) or not all(
            isinstance(value, str) and value.strip() for value in referenced_value
        ):
            raise TypeError("referenced_job_ids must be a non-empty string list")

        goals = tuple(CareerIntentGoal(value) for value in goals_value)
        return CareerIntent(
            goals=goals,
            referenced_job_ids=tuple(referenced_value),
            current_job_required=_strict_bool(payload, "current_job_required", False),
            needs_clarification=_strict_bool(payload, "needs_clarification", False),
            clarification_question=_optional_string(payload, "clarification_question"),
            unsupported_request=_optional_string(payload, "unsupported_request"),
            confidence=_optional_confidence(payload),
            reasoning_summary=_optional_string(payload, "reasoning_summary") or "",
        )


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
                    goals=(),
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


def _strict_bool(payload: dict[str, object], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean")
    return value


def _optional_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be a non-empty string or null")
    return value.strip()


def _optional_confidence(payload: dict[str, object]) -> float | None:
    value = payload.get("confidence")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("confidence must be numeric or null")
    return float(value)


__all__ = [
    "CareerIntent",
    "CareerIntentGoal",
    "CareerIntentModel",
    "CareerIntentResolutionContext",
    "CareerIntentRouter",
    "CareerIntentResolver",
    "CareerIntentValidationError",
]
