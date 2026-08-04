"""Pure readiness policy for credential-backed Requirement acceptance work."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.requirement_acceptance.runs import (
    RequirementAcceptanceCanaryDecision,
    RequirementAcceptancePreflight,
    RequirementAcceptanceRunDetail,
)


class RequirementAcceptanceReadinessBlockerScope(StrEnum):
    WORKFLOW = "workflow"
    PROVIDER_EXECUTION = "provider_execution"


class RequirementAcceptanceReadinessNextAction(StrEnum):
    FIX_BLOCKERS = "fix_blockers"
    RUN_CANARY = "run_canary"
    REVIEW_CANARY = "review_canary"
    RESUME_RUN = "resume_run"
    OPEN_MANUAL_REVIEW = "open_manual_review"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceReadinessBlocker:
    scope: RequirementAcceptanceReadinessBlockerScope
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceReadinessResult:
    dataset_fingerprint: str | None
    source_version: str | None
    selected_count: int
    provider: str
    model: str
    api_key_configured: bool
    reviewer: str
    title: str
    requested_max_new_extractions: int | None
    database_reachable: bool
    database_revision: str | None
    migration_head: str
    workflow_ready: bool
    provider_execution_allowed: bool
    ready_for_next_action: bool
    next_action: RequirementAcceptanceReadinessNextAction
    run_id: str | None
    run_status: str | None
    attempted_calls: int
    canary_decision: RequirementAcceptanceCanaryDecision | None
    batch_id: str | None
    workbench_url: str | None
    manual_review_url: str | None
    blockers: tuple[RequirementAcceptanceReadinessBlocker, ...]


def evaluate_requirement_acceptance_readiness(
    *,
    preflight: RequirementAcceptancePreflight | None,
    provider: str,
    model: str,
    api_key_configured: bool,
    reviewer: str,
    title: str,
    max_new_extractions: int | None,
    database_reachable: bool,
    database_revision: str | None,
    migration_head: str,
    existing_run: RequirementAcceptanceRunDetail | None,
    web_base_url: str,
    database_error: str | None = None,
    dataset_blocker_code: str | None = None,
    dataset_blocker_message: str | None = None,
) -> RequirementAcceptanceReadinessResult:
    """Evaluate the next safe action without writing data or calling a Provider."""

    normalized_provider = provider.strip().casefold() or "disabled"
    normalized_model = model.strip()
    normalized_reviewer = reviewer.strip()
    normalized_title = title.strip()
    normalized_web_base_url = web_base_url.rstrip("/")
    blockers: list[RequirementAcceptanceReadinessBlocker] = []

    def block(
        scope: RequirementAcceptanceReadinessBlockerScope,
        code: str,
        message: str,
    ) -> None:
        blockers.append(
            RequirementAcceptanceReadinessBlocker(
                scope=scope,
                code=code,
                message=message,
            )
        )

    if preflight is None:
        block(
            RequirementAcceptanceReadinessBlockerScope.WORKFLOW,
            dataset_blocker_code or "formal_dataset_missing",
            dataset_blocker_message
            or "No canonical private formal Requirement acceptance dataset is available.",
        )

    if not database_reachable:
        block(
            RequirementAcceptanceReadinessBlockerScope.WORKFLOW,
            "database_unreachable",
            database_error or "The configured database could not be opened for a read-only readiness check.",
        )
    elif database_revision != migration_head:
        block(
            RequirementAcceptanceReadinessBlockerScope.WORKFLOW,
            "database_migration_not_current",
            (
                f"Database revision is {database_revision or 'missing'}; "
                f"Requirement acceptance requires Alembic head {migration_head}. "
                "Run `.venv/bin/alembic upgrade head` from services/backend, then rerun readiness."
            ),
        )

    if normalized_provider != "openai":
        block(
            RequirementAcceptanceReadinessBlockerScope.WORKFLOW,
            "live_provider_not_configured",
            "Set REQUIREMENT_EXTRACTOR_PROVIDER=openai for formal live evidence.",
        )
    if not normalized_model:
        block(
            RequirementAcceptanceReadinessBlockerScope.WORKFLOW,
            "live_model_not_configured",
            "Set a non-blank REQUIREMENT_EXTRACTOR_MODEL.",
        )
    if not normalized_reviewer:
        block(
            RequirementAcceptanceReadinessBlockerScope.WORKFLOW,
            "reviewer_missing",
            "Provide --reviewer so the Run identity and human decision owner are stable.",
        )
    if not normalized_title:
        block(
            RequirementAcceptanceReadinessBlockerScope.WORKFLOW,
            "title_missing",
            "Provide or derive a non-blank Run title.",
        )

    workflow_ready = not any(
        item.scope is RequirementAcceptanceReadinessBlockerScope.WORKFLOW
        for item in blockers
    )

    next_action = RequirementAcceptanceReadinessNextAction.FIX_BLOCKERS
    if workflow_ready:
        if existing_run is None:
            next_action = RequirementAcceptanceReadinessNextAction.RUN_CANARY
        elif existing_run.batch_id is not None:
            next_action = RequirementAcceptanceReadinessNextAction.OPEN_MANUAL_REVIEW
        elif (
            existing_run.canary_review is not None
            and existing_run.canary_review.decision
            is RequirementAcceptanceCanaryDecision.STOP
        ):
            next_action = RequirementAcceptanceReadinessNextAction.STOPPED
        elif existing_run.canary_review_required:
            next_action = RequirementAcceptanceReadinessNextAction.REVIEW_CANARY
        elif (
            existing_run.canary_review is not None
            and existing_run.canary_review.decision
            is RequirementAcceptanceCanaryDecision.CONTINUE
        ):
            next_action = RequirementAcceptanceReadinessNextAction.RESUME_RUN
        else:
            next_action = RequirementAcceptanceReadinessNextAction.RUN_CANARY

    if next_action in {
        RequirementAcceptanceReadinessNextAction.RUN_CANARY,
        RequirementAcceptanceReadinessNextAction.RESUME_RUN,
    }:
        if not api_key_configured:
            block(
                RequirementAcceptanceReadinessBlockerScope.PROVIDER_EXECUTION,
                "openai_api_key_missing",
                "Set OPENAI_API_KEY before a live Provider call. The key value is never printed.",
            )
        if max_new_extractions is None:
            block(
                RequirementAcceptanceReadinessBlockerScope.PROVIDER_EXECUTION,
                "max_new_extractions_missing",
                "Provide an explicit --max-new-extractions limit.",
            )
        elif not 1 <= max_new_extractions <= 20:
            block(
                RequirementAcceptanceReadinessBlockerScope.PROVIDER_EXECUTION,
                "max_new_extractions_out_of_range",
                "--max-new-extractions must be between 1 and 20.",
            )
        elif (
            next_action is RequirementAcceptanceReadinessNextAction.RUN_CANARY
            and existing_run is None
            and max_new_extractions > 3
        ):
            block(
                RequirementAcceptanceReadinessBlockerScope.PROVIDER_EXECUTION,
                "initial_canary_limit_exceeded",
                "The first live invocation may request at most 3 new Extractions.",
            )
        elif (
            next_action is RequirementAcceptanceReadinessNextAction.RUN_CANARY
            and existing_run is not None
            and existing_run.canary_review is None
        ):
            remaining = max(0, 3 - existing_run.attempted_calls)
            if max_new_extractions > remaining:
                block(
                    RequirementAcceptanceReadinessBlockerScope.PROVIDER_EXECUTION,
                    "remaining_canary_limit_exceeded",
                    (
                        f"This Run has {remaining} unreviewed Canary call(s) remaining; "
                        "submit the human decision before requesting more."
                    ),
                )

    provider_execution_allowed = (
        workflow_ready
        and next_action
        in {
            RequirementAcceptanceReadinessNextAction.RUN_CANARY,
            RequirementAcceptanceReadinessNextAction.RESUME_RUN,
        }
        and not any(
            item.scope
            is RequirementAcceptanceReadinessBlockerScope.PROVIDER_EXECUTION
            for item in blockers
        )
    )
    ready_for_next_action = workflow_ready and (
        provider_execution_allowed
        or next_action
        in {
            RequirementAcceptanceReadinessNextAction.REVIEW_CANARY,
            RequirementAcceptanceReadinessNextAction.OPEN_MANUAL_REVIEW,
        }
    )

    run_id = existing_run.id if existing_run is not None else None
    workbench_url = (
        f"{normalized_web_base_url}/evals/requirements/canary/{run_id}"
        if run_id is not None
        else None
    )
    manual_review_url = (
        f"{normalized_web_base_url}/evals/requirements/manual/{existing_run.batch_id}"
        if existing_run is not None and existing_run.batch_id is not None
        else None
    )

    return RequirementAcceptanceReadinessResult(
        dataset_fingerprint=(
            preflight.dataset_fingerprint if preflight is not None else None
        ),
        source_version=preflight.source_version if preflight is not None else None,
        selected_count=preflight.selected_count if preflight is not None else 0,
        provider=normalized_provider,
        model=normalized_model,
        api_key_configured=api_key_configured,
        reviewer=normalized_reviewer,
        title=normalized_title,
        requested_max_new_extractions=max_new_extractions,
        database_reachable=database_reachable,
        database_revision=database_revision,
        migration_head=migration_head,
        workflow_ready=workflow_ready,
        provider_execution_allowed=provider_execution_allowed,
        ready_for_next_action=ready_for_next_action,
        next_action=next_action,
        run_id=run_id,
        run_status=existing_run.status.value if existing_run is not None else None,
        attempted_calls=existing_run.attempted_calls if existing_run is not None else 0,
        canary_decision=(
            existing_run.canary_review.decision
            if existing_run is not None and existing_run.canary_review is not None
            else None
        ),
        batch_id=existing_run.batch_id if existing_run is not None else None,
        workbench_url=workbench_url,
        manual_review_url=manual_review_url,
        blockers=tuple(blockers),
    )
