"""Pure policy for the controlled Requirement acceptance resume boundary."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessNextAction,
    RequirementAcceptanceReadinessResult,
)
from app.application.requirement_acceptance.runs import (
    RequirementAcceptanceCanaryDecision,
    RequirementAcceptanceRunDetail,
)


class RequirementAcceptanceResumeOperatorError(RuntimeError):
    """Raised when the controlled resume boundary becomes unsafe."""


class RequirementAcceptanceResumeOperatorState(StrEnum):
    BLOCKED = "blocked"
    READY_FOR_EXPLICIT_EXECUTION = "ready_for_explicit_execution"
    AUTHORIZED = "authorized"


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceResumeOperatorBlocker:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceResumeOperatorPlan:
    state: RequirementAcceptanceResumeOperatorState
    dataset_path: Path
    expected_dataset_path: Path
    private_root: Path
    session_manifest_path: Path | None
    execute_requested: bool
    live_cost_confirmed: bool
    expected_run_id: str
    expected_canary_review_id: str
    run_id: str | None
    canary_review_id: str | None
    requested_max_new_extractions: int | None
    attempted_calls_before: int
    completed_case_count_before: int
    remaining_case_count_before: int
    plan_ready: bool
    execution_authorized: bool
    blockers: tuple[RequirementAcceptanceResumeOperatorBlocker, ...]


def evaluate_requirement_acceptance_resume_operator(
    *,
    readiness: RequirementAcceptanceReadinessResult,
    existing_run: RequirementAcceptanceRunDetail | None,
    dataset_path: Path,
    expected_dataset_path: Path,
    private_root: Path,
    session_manifest_path: Path | None,
    expected_run_id: str,
    expected_canary_review_id: str,
    execute_requested: bool,
    live_cost_confirmed: bool,
) -> RequirementAcceptanceResumeOperatorPlan:
    """Decide whether one explicit post-Continue resume invocation may run."""

    dataset = dataset_path.resolve()
    expected_dataset = expected_dataset_path.resolve()
    private = private_root.resolve()
    manifest = session_manifest_path.resolve() if session_manifest_path else None
    normalized_expected_run_id = expected_run_id.strip()
    normalized_expected_review_id = expected_canary_review_id.strip()
    blockers: list[RequirementAcceptanceResumeOperatorBlocker] = []

    def block(code: str, message: str) -> None:
        blockers.append(
            RequirementAcceptanceResumeOperatorBlocker(code=code, message=message)
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

    if readiness.next_action is not RequirementAcceptanceReadinessNextAction.RESUME_RUN:
        block(
            "next_action_is_not_resume_run",
            (
                "This command may only resume after an immutable Continue decision; "
                f"current nextAction={readiness.next_action.value}."
            ),
        )
    if not readiness.provider_execution_allowed:
        block(
            "provider_execution_not_allowed",
            "Readiness did not authorize a new live Provider invocation.",
        )
    if existing_run is None:
        block(
            "acceptance_run_missing",
            "Controlled resume requires an existing Requirement acceptance Run.",
        )

    run_id = existing_run.id if existing_run is not None else None
    if existing_run is not None:
        if existing_run.dataset_fingerprint != readiness.dataset_fingerprint:
            block(
                "run_dataset_fingerprint_mismatch",
                "The loaded Run does not belong to the readiness dataset fingerprint.",
            )
        if existing_run.title != readiness.title:
            block(
                "run_title_mismatch",
                "The loaded Run title does not match the readiness identity.",
            )
        if existing_run.reviewer != readiness.reviewer:
            block(
                "run_reviewer_mismatch",
                "The loaded Run reviewer does not match the readiness identity.",
            )
        if existing_run.provider.strip().casefold() != readiness.provider:
            block(
                "run_provider_mismatch",
                "The loaded Run provider does not match the readiness cohort.",
            )
        if existing_run.model != readiness.model:
            block(
                "run_model_mismatch",
                "The loaded Run model does not match the readiness cohort.",
            )
        if existing_run.batch_id is not None:
            block(
                "run_already_has_manual_review_batch",
                "The Run already has a frozen Manual Review Batch and must not resume.",
            )

    review = existing_run.canary_review if existing_run is not None else None
    review_id = review.id if review is not None else None
    completed_case_count = (
        existing_run.completed_case_count if existing_run is not None else 0
    )
    remaining_case_count = (
        max(0, len(existing_run.cases) - completed_case_count)
        if existing_run is not None
        else 0
    )

    if not normalized_expected_run_id:
        block(
            "expected_run_id_missing",
            "Pass the exact Run ID that was inspected during Canary review.",
        )
    elif run_id is not None and normalized_expected_run_id != run_id:
        block(
            "expected_run_id_mismatch",
            "The expected Run ID does not match the readiness Run.",
        )
    if readiness.run_id is not None and run_id is not None and readiness.run_id != run_id:
        block(
            "readiness_run_id_mismatch",
            "Readiness and the loaded Run do not reference the same immutable identity.",
        )

    if review is None:
        block(
            "continue_review_missing",
            "Controlled resume requires an immutable Canary Continue review.",
        )
    else:
        if review.decision is not RequirementAcceptanceCanaryDecision.CONTINUE:
            block(
                "canary_decision_is_not_continue",
                "Only an immutable Continue decision authorizes controlled resume.",
            )
        if review.run_id != existing_run.id:
            block(
                "canary_review_run_mismatch",
                "The Canary review does not belong to the loaded Run.",
            )
        if review.reviewer != existing_run.reviewer or review.reviewer != readiness.reviewer:
            block(
                "canary_reviewer_mismatch",
                "The immutable Canary reviewer does not match the Run/readiness owner.",
            )
        if not normalized_expected_review_id:
            block(
                "expected_canary_review_id_missing",
                "Pass the exact immutable Canary review ID that authorized Continue.",
            )
        elif normalized_expected_review_id != review.id:
            block(
                "expected_canary_review_id_mismatch",
                "The expected Canary review ID does not match the immutable decision.",
            )

        cases_by_id = {case.id: case for case in existing_run.cases}
        reviewed_cases = tuple(
            cases_by_id[case_id]
            for case_id in review.reviewed_case_ids
            if case_id in cases_by_id
        )
        if not review.reviewed_case_ids:
            block(
                "canary_review_evidence_empty",
                "The Continue decision must freeze at least one attempted Canary case.",
            )
        elif len(reviewed_cases) != len(review.reviewed_case_ids):
            block(
                "canary_review_case_evidence_missing",
                "One or more frozen Canary case IDs are absent from the Run.",
            )
        elif any(not case.was_attempted for case in reviewed_cases):
            block(
                "canary_review_case_not_attempted",
                "Every frozen Canary case must still prove a persisted attempt.",
            )
        else:
            if not review.reviewed_extraction_ids:
                block(
                    "canary_continue_has_no_extraction_evidence",
                    "A Continue decision must freeze at least one successful Extraction ID.",
                )
            if len(review.reviewed_trace_run_ids) != len(review.reviewed_case_ids):
                block(
                    "canary_review_trace_evidence_incomplete",
                    "Every frozen Canary case must have one reviewed Trace ID.",
                )

            review_snapshot_is_current = (
                existing_run.attempted_calls == len(review.reviewed_case_ids)
                and all(case.attempt_count == 1 for case in reviewed_cases)
            )
            if review_snapshot_is_current:
                frozen_extractions = tuple(
                    case.extraction_id
                    for case in reviewed_cases
                    if case.extraction_id is not None
                )
                frozen_traces = tuple(
                    case.trace_run_id
                    for case in reviewed_cases
                    if case.trace_run_id is not None
                )
                if frozen_extractions != review.reviewed_extraction_ids:
                    block(
                        "canary_review_extraction_evidence_mismatch",
                        "Frozen Canary Extraction IDs do not match the pre-resume cases.",
                    )
                if frozen_traces != review.reviewed_trace_run_ids:
                    block(
                        "canary_review_trace_evidence_mismatch",
                        "Frozen Canary Trace IDs do not match the pre-resume cases.",
                    )

    requested = readiness.requested_max_new_extractions
    if requested is None or requested < 1:
        block(
            "resume_budget_missing_or_invalid",
            "Controlled resume requires an explicit positive new-extraction budget.",
        )
    elif remaining_case_count == 0:
        block(
            "no_remaining_cases",
            "The Run has no remaining Cases that require resume work.",
        )
    elif requested > remaining_case_count:
        block(
            "resume_budget_exceeds_remaining_cases",
            (
                f"Requested {requested} new Extractions, but only "
                f"{remaining_case_count} Cases remain incomplete."
            ),
        )

    plan_ready = not blockers
    if execute_requested and not live_cost_confirmed:
        block(
            "review_and_live_cost_confirmation_missing",
            (
                "Pass the explicit confirmation that the immutable Continue evidence "
                "was reviewed and that this resume may incur live Provider cost."
            ),
        )

    execution_authorized = (
        plan_ready
        and execute_requested
        and live_cost_confirmed
        and not blockers
    )
    if execution_authorized:
        state = RequirementAcceptanceResumeOperatorState.AUTHORIZED
    elif plan_ready:
        state = RequirementAcceptanceResumeOperatorState.READY_FOR_EXPLICIT_EXECUTION
    else:
        state = RequirementAcceptanceResumeOperatorState.BLOCKED

    return RequirementAcceptanceResumeOperatorPlan(
        state=state,
        dataset_path=dataset,
        expected_dataset_path=expected_dataset,
        private_root=private,
        session_manifest_path=manifest,
        execute_requested=execute_requested,
        live_cost_confirmed=live_cost_confirmed,
        expected_run_id=normalized_expected_run_id,
        expected_canary_review_id=normalized_expected_review_id,
        run_id=run_id,
        canary_review_id=review_id,
        requested_max_new_extractions=requested,
        attempted_calls_before=(existing_run.attempted_calls if existing_run else 0),
        completed_case_count_before=completed_case_count,
        remaining_case_count_before=remaining_case_count,
        plan_ready=plan_ready,
        execution_authorized=execution_authorized,
        blockers=tuple(blockers),
    )
