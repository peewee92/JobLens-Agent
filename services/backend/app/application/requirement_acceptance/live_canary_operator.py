"""Pure policy for the explicit live Requirement Canary operator boundary."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessNextAction,
    RequirementAcceptanceReadinessResult,
)


class RequirementAcceptanceCanaryOperatorError(RuntimeError):
    """Raised when the live Canary operator boundary becomes unsafe."""


class RequirementAcceptanceCanaryOperatorState(StrEnum):
    BLOCKED = "blocked"
    READY_FOR_EXPLICIT_EXECUTION = "ready_for_explicit_execution"
    AUTHORIZED = "authorized"


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceCanaryOperatorBlocker:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceCanaryOperatorPlan:
    state: RequirementAcceptanceCanaryOperatorState
    dataset_path: Path
    expected_dataset_path: Path
    private_root: Path
    session_manifest_path: Path | None
    execute_requested: bool
    live_cost_confirmed: bool
    plan_ready: bool
    execution_authorized: bool
    requested_max_new_extractions: int | None
    attempted_calls_before: int
    blockers: tuple[RequirementAcceptanceCanaryOperatorBlocker, ...]


def evaluate_requirement_acceptance_canary_operator(
    *,
    readiness: RequirementAcceptanceReadinessResult,
    dataset_path: Path,
    expected_dataset_path: Path,
    private_root: Path,
    session_manifest_path: Path | None,
    execute_requested: bool,
    live_cost_confirmed: bool,
) -> RequirementAcceptanceCanaryOperatorPlan:
    """Decide whether one explicit initial/partial Canary invocation may run.

    This policy does not call a Provider or write data.  It deliberately permits
    only the pre-human-review Canary phase.  Controlled resume after an immutable
    Continue decision remains a separate operator action.
    """

    dataset = dataset_path.resolve()
    expected_dataset = expected_dataset_path.resolve()
    private = private_root.resolve()
    manifest = session_manifest_path.resolve() if session_manifest_path else None
    blockers: list[RequirementAcceptanceCanaryOperatorBlocker] = []

    def block(code: str, message: str) -> None:
        blockers.append(
            RequirementAcceptanceCanaryOperatorBlocker(code=code, message=message)
        )

    if not dataset.is_relative_to(private):
        block(
            "dataset_outside_private_root",
            "The formal dataset must be staged under the configured private root.",
        )
    if dataset != expected_dataset:
        block(
            "dataset_not_canonical_private_handoff",
            (
                "The dataset path does not match the fingerprint-addressed private "
                "handoff path produced by the guarded Bootstrap."
            ),
        )
    if manifest is not None and not manifest.is_relative_to(private):
        block(
            "session_manifest_outside_private_root",
            "The Session Manifest must remain under the configured private root.",
        )

    if readiness.next_action is not RequirementAcceptanceReadinessNextAction.RUN_CANARY:
        block(
            "next_action_is_not_run_canary",
            (
                "This command may only perform the initial/partial Canary phase; "
                f"current nextAction={readiness.next_action.value}."
            ),
        )
    if not readiness.provider_execution_allowed:
        block(
            "provider_execution_not_allowed",
            "Readiness did not authorize a new live Provider invocation.",
        )

    requested = readiness.requested_max_new_extractions
    if requested is None or not 1 <= requested <= 3:
        block(
            "canary_budget_must_be_one_to_three",
            "The operator command requires an explicit 1-3 new-extraction budget.",
        )

    plan_ready = not blockers
    if execute_requested and not live_cost_confirmed:
        block(
            "live_cost_confirmation_missing",
            (
                "Pass the explicit live-cost-and-human-review confirmation before "
                "the command may call the Provider."
            ),
        )

    execution_authorized = (
        plan_ready
        and execute_requested
        and live_cost_confirmed
        and not blockers
    )
    if execution_authorized:
        state = RequirementAcceptanceCanaryOperatorState.AUTHORIZED
    elif plan_ready:
        state = RequirementAcceptanceCanaryOperatorState.READY_FOR_EXPLICIT_EXECUTION
    else:
        state = RequirementAcceptanceCanaryOperatorState.BLOCKED

    return RequirementAcceptanceCanaryOperatorPlan(
        state=state,
        dataset_path=dataset,
        expected_dataset_path=expected_dataset,
        private_root=private,
        session_manifest_path=manifest,
        execute_requested=execute_requested,
        live_cost_confirmed=live_cost_confirmed,
        plan_ready=plan_ready,
        execution_authorized=execution_authorized,
        requested_max_new_extractions=requested,
        attempted_calls_before=readiness.attempted_calls,
        blockers=tuple(blockers),
    )
