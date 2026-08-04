"""Plan or explicitly execute one initial/partial live Requirement Canary invocation."""
from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.application.requirement_acceptance import (
    InvalidRequirementAcceptanceDatasetError,
    RequirementAcceptanceCanaryGateError,
    RequirementAcceptanceExecutionLeaseLostError,
    RequirementAcceptanceExecutionLeaseUnavailableError,
    RequirementAcceptanceImportError,
    preflight_requirement_acceptance_dataset,
)
from app.application.requirement_acceptance.live_canary_operator import (
    RequirementAcceptanceCanaryOperatorError,
    RequirementAcceptanceCanaryOperatorPlan,
    evaluate_requirement_acceptance_canary_operator,
)
from app.application.requirement_acceptance.local_bootstrap import (
    file_sha256,
    private_dataset_path,
)
from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessNextAction,
    evaluate_requirement_acceptance_readiness,
)
from app.application.requirement_acceptance.session_manifest import (
    build_requirement_acceptance_session_manifest,
    requirement_acceptance_session_id,
    write_requirement_acceptance_session_manifest,
)
from app.core.config import get_settings
from app.workflows.job_requirement_extraction import EXTRACTOR_VERSION, PROMPT_VERSION
from scripts.bootstrap_requirement_acceptance import DEFAULT_PRIVATE_ROOT, PRIVATE_DATA_ROOT
from scripts.check_requirement_acceptance_readiness import (
    _database_revision,
    _default_title,
    _existing_run,
    _load_payload,
    _migration_head,
    _summary as readiness_summary,
)
from scripts.prepare_requirement_acceptance import _build_use_case, _summary_dict


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--title")
    parser.add_argument("--max-new-extractions", type=int, required=True)
    parser.add_argument("--web-base-url", default="http://localhost:3000")
    parser.add_argument(
        "--private-root",
        type=Path,
        default=DEFAULT_PRIVATE_ROOT,
        help="Git-ignored private Requirement acceptance root.",
    )
    parser.add_argument(
        "--session-manifest",
        type=Path,
        help="Optional private manifest path; execute mode derives one when omitted.",
    )
    parser.add_argument(
        "--execute-canary",
        action="store_true",
        help="Actually import the formal cohort and allow up to the explicit live budget.",
    )
    parser.add_argument(
        "--confirm-live-cost-and-human-review",
        action="store_true",
        help=(
            "Acknowledge live Provider cost and that the operator must personally "
            "review the Canary evidence before any controlled resume."
        ),
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _operator_command_preview(
    *,
    dataset: Path,
    reviewer: str,
    title: str,
    max_new_extractions: int,
    private_root: Path,
    session_manifest: Path,
) -> str:
    return shlex.join(
        [
            ".venv/bin/python",
            "-m",
            "scripts.operate_requirement_acceptance_canary",
            str(dataset.resolve()),
            "--reviewer",
            reviewer,
            "--title",
            title,
            "--max-new-extractions",
            str(max_new_extractions),
            "--private-root",
            str(private_root.resolve()),
            "--session-manifest",
            str(session_manifest.resolve()),
            "--execute-canary",
            "--confirm-live-cost-and-human-review",
            "--json",
        ]
    )


def _assess_readiness(
    *,
    preflight,
    reviewer: str,
    title: str,
    max_new_extractions: int,
    web_base_url: str,
    settings,
):
    provider = settings.requirement_extractor_provider.strip().casefold() or "disabled"
    model = settings.requirement_extractor_model.strip()
    head = _migration_head()
    database_reachable, database_revision, database_error = _database_revision(
        settings.database_url
    )
    existing_run = None
    if (
        database_reachable
        and database_revision == head
        and provider == "openai"
        and model
        and reviewer
        and title
    ):
        try:
            existing_run = _existing_run(
                dataset_fingerprint=preflight.dataset_fingerprint,
                title=title,
                reviewer=reviewer,
                provider=provider,
                model=model,
            )
        except (SQLAlchemyError, RuntimeError) as error:
            database_reachable = False
            database_error = f"Acceptance Run query failed: {type(error).__name__}"

    readiness = evaluate_requirement_acceptance_readiness(
        preflight=preflight,
        provider=provider,
        model=model,
        api_key_configured=bool(
            settings.openai_api_key and settings.openai_api_key.strip()
        ),
        reviewer=reviewer,
        title=title,
        max_new_extractions=max_new_extractions,
        database_reachable=database_reachable,
        database_revision=database_revision,
        migration_head=head,
        existing_run=existing_run,
        web_base_url=web_base_url,
        database_error=database_error,
    )
    return readiness, existing_run


def _default_manifest_path(
    *,
    private_root: Path,
    readiness,
) -> Path:
    session_id = requirement_acceptance_session_id(
        dataset_fingerprint=readiness.dataset_fingerprint,
        reviewer=readiness.reviewer,
        title=readiness.title,
        provider=readiness.provider,
        model=readiness.model,
        extractor_version=EXTRACTOR_VERSION,
        prompt_version=PROMPT_VERSION,
    )
    return private_root / "session-manifests" / f"{session_id}.json"


def _operator_plan_summary(plan: RequirementAcceptanceCanaryOperatorPlan) -> dict[str, Any]:
    return {
        "state": plan.state.value,
        "planReady": plan.plan_ready,
        "executionAuthorized": plan.execution_authorized,
        "executeRequested": plan.execute_requested,
        "liveCostConfirmed": plan.live_cost_confirmed,
        "datasetPath": str(plan.dataset_path),
        "expectedDatasetPath": str(plan.expected_dataset_path),
        "privateRoot": str(plan.private_root),
        "sessionManifestPath": (
            str(plan.session_manifest_path) if plan.session_manifest_path else None
        ),
        "requestedMaxNewExtractions": plan.requested_max_new_extractions,
        "attemptedCallsBefore": plan.attempted_calls_before,
        "blockers": [
            {"code": blocker.code, "message": blocker.message}
            for blocker in plan.blockers
        ],
    }


def _attempt_counts(existing_run) -> dict[str, int]:
    if existing_run is None:
        return {}
    return {case.id: case.attempt_count for case in existing_run.cases}


def _new_attempt_evidence(existing_run, before: dict[str, int]) -> list[dict[str, Any]]:
    if existing_run is None:
        return []
    evidence = []
    for case in existing_run.cases:
        previous = before.get(case.id, 0)
        if case.attempt_count <= previous:
            continue
        evidence.append(
            {
                "caseId": case.id,
                "caseIndex": case.case_index,
                "jobId": case.job_id,
                "status": case.status.value,
                "attemptDelta": case.attempt_count - previous,
                "extractionId": case.extraction_id,
                "traceRunId": case.trace_run_id,
                "errorCode": case.error_code,
            }
        )
    return evidence


def _write_manifest(
    *,
    path: Path,
    private_root: Path,
    readiness,
    existing_run,
    dataset: Path,
    recommended_command: str | None,
) -> None:
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(private_root.resolve()):
        raise RequirementAcceptanceCanaryOperatorError(
            "Session Manifest path escaped the configured private root at write time."
        )
    manifest = build_requirement_acceptance_session_manifest(
        readiness=readiness,
        existing_run=existing_run,
        dataset_path=dataset,
        extractor_version=EXTRACTOR_VERSION,
        prompt_version=PROMPT_VERSION,
        recommended_command=recommended_command,
    )
    write_requirement_acceptance_session_manifest(resolved_path, manifest)


def _emit(summary: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    operator = summary["operator"]
    print(
        "Requirement acceptance Canary operator "
        f"state={operator['state']} executionAuthorized="
        f"{operator['executionAuthorized']} liveAttempts="
        f"{summary.get('liveExtractionAttemptsObserved', 0)}"
    )
    for blocker in operator["blockers"]:
        print(f"- {blocker['code']}: {blocker['message']}")
    if summary.get("workbenchUrl"):
        print(f"Workbench: {summary['workbenchUrl']}")
    if summary.get("sessionManifestPath"):
        print(f"Session manifest: {summary['sessionManifestPath']}")


def main() -> int:
    args = _arguments()
    private_root = args.private_root.resolve()
    if not private_root.is_relative_to(PRIVATE_DATA_ROOT):
        print(
            "Canary operator rejected: --private-root must stay under "
            f"{PRIVATE_DATA_ROOT}"
        )
        return 2

    dataset_path = args.dataset.resolve()
    if not dataset_path.is_relative_to(private_root):
        print(
            "Canary operator rejected: dataset must be staged under the selected "
            f"private root {private_root}"
        )
        return 2

    try:
        payload = _load_payload(dataset_path)
        preflight = preflight_requirement_acceptance_dataset(payload)
    except InvalidRequirementAcceptanceDatasetError as error:
        print(f"Canary operator rejected: {error}")
        return 2

    dataset_file_sha256_before = file_sha256(dataset_path)
    dataset_byte_count_before = dataset_path.stat().st_size

    reviewer = args.reviewer.strip()
    title = (args.title or _default_title(payload, dataset_path)).strip()
    settings = get_settings()
    readiness, existing_run = _assess_readiness(
        preflight=preflight,
        reviewer=reviewer,
        title=title,
        max_new_extractions=args.max_new_extractions,
        web_base_url=args.web_base_url,
        settings=settings,
    )
    expected_dataset = private_dataset_path(
        private_root=private_root,
        dataset_fingerprint=preflight.dataset_fingerprint,
    )
    manifest_path = (
        args.session_manifest.resolve()
        if args.session_manifest is not None
        else _default_manifest_path(private_root=private_root, readiness=readiness).resolve()
    )
    plan = evaluate_requirement_acceptance_canary_operator(
        readiness=readiness,
        dataset_path=dataset_path,
        expected_dataset_path=expected_dataset,
        private_root=private_root,
        session_manifest_path=manifest_path,
        execute_requested=args.execute_canary,
        live_cost_confirmed=args.confirm_live_cost_and_human_review,
    )
    command_preview = None
    if plan.plan_ready:
        command_preview = _operator_command_preview(
            dataset=dataset_path,
            reviewer=reviewer,
            title=title,
            max_new_extractions=args.max_new_extractions,
            private_root=private_root,
            session_manifest=manifest_path,
        )

    summary: dict[str, Any] = {
        "operator": _operator_plan_summary(plan),
        "datasetFileSha256": dataset_file_sha256_before,
        "datasetByteCount": dataset_byte_count_before,
        "datasetFileChangedDuringExecution": False,
        "preReadiness": readiness_summary(
            readiness,
            recommended_command=command_preview,
        ),
        "executionOutcome": "not_executed",
        "preparation": None,
        "postReadiness": None,
        "newAttemptEvidence": [],
        "liveExtractionAttemptsObserved": 0,
        "missingTraceCaseIds": [],
        "attemptBudgetExceeded": False,
        "sessionManifestPath": None,
        "sessionManifestWrittenBeforeExecution": False,
        "sessionManifestUpdatedAfterExecution": False,
        "workbenchUrl": readiness.workbench_url,
        "manualHumanDecisionRequired": (
            readiness.next_action
            is RequirementAcceptanceReadinessNextAction.REVIEW_CANARY
        ),
        "automaticCanaryDecisionSubmitted": False,
    }

    should_write_plan_manifest = (
        (args.session_manifest is not None or args.execute_canary)
        and plan.plan_ready
    )
    if should_write_plan_manifest:
        try:
            _write_manifest(
                path=manifest_path,
                private_root=private_root,
                readiness=readiness,
                existing_run=existing_run,
                dataset=dataset_path,
                recommended_command=command_preview,
            )
        except (OSError, RequirementAcceptanceCanaryOperatorError) as error:
            summary["executionOutcome"] = "pre_execution_manifest_write_failed"
            summary["manifestError"] = type(error).__name__
            _emit(summary, json_output=args.json)
            return 2
        summary["sessionManifestPath"] = str(manifest_path)
        summary["sessionManifestWrittenBeforeExecution"] = True

    if not args.execute_canary:
        summary["executionOutcome"] = (
            "ready_for_explicit_execution" if plan.plan_ready else "blocked"
        )
        _emit(summary, json_output=args.json)
        return 0 if plan.plan_ready else 1

    if not plan.execution_authorized:
        summary["executionOutcome"] = "blocked"
        _emit(summary, json_output=args.json)
        return 2

    before_counts = _attempt_counts(existing_run)
    try:
        use_case, _runtime_settings = _build_use_case()
        preparation = use_case.execute(
            payload=payload,
            title=title,
            reviewer=reviewer,
            max_new_extractions=args.max_new_extractions,
        )
    except (
        InvalidRequirementAcceptanceDatasetError,
        RequirementAcceptanceCanaryGateError,
        RequirementAcceptanceExecutionLeaseUnavailableError,
        RequirementAcceptanceImportError,
    ) as error:
        summary["executionOutcome"] = "execution_rejected"
        summary["executionError"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
        _emit(summary, json_output=args.json)
        return 2
    except RequirementAcceptanceExecutionLeaseLostError as error:
        summary["executionOutcome"] = "completed_with_attention_required"
        summary["executionError"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
        _emit(summary, json_output=args.json)
        return 1

    summary["preparation"] = _summary_dict(preparation)
    try:
        post_existing_run = _existing_run(
            dataset_fingerprint=preflight.dataset_fingerprint,
            title=title,
            reviewer=reviewer,
            provider=preparation.provider,
            model=preparation.model,
        )
    except (SQLAlchemyError, RuntimeError) as error:
        summary["executionOutcome"] = "completed_with_attention_required"
        summary["postExecutionEvidenceError"] = {
            "type": type(error).__name__,
            "message": "Executed Canary Run could not be read after preparation.",
        }
        summary["liveExtractionAttemptsObserved"] = None
        _emit(summary, json_output=args.json)
        return 1
    if post_existing_run is None:
        summary["executionOutcome"] = "completed_with_attention_required"
        summary["postExecutionEvidenceError"] = {
            "type": "run_not_found",
            "message": "Executed Canary Run could not be read after preparation.",
        }
        summary["liveExtractionAttemptsObserved"] = None
        _emit(summary, json_output=args.json)
        return 1
    if post_existing_run.id != preparation.run_id:
        summary["executionOutcome"] = "completed_with_attention_required"
        summary["postExecutionEvidenceError"] = {
            "type": "run_identity_mismatch",
            "message": (
                "Executed Canary Run identity does not match the Preparation result."
            ),
        }
        summary["liveExtractionAttemptsObserved"] = None
        _emit(summary, json_output=args.json)
        return 1
    if preparation.provider != readiness.provider or preparation.model != readiness.model:
        summary["executionOutcome"] = "completed_with_attention_required"
        summary["postExecutionEvidenceError"] = {
            "type": "cohort_mismatch",
            "message": (
                "Executed Canary cohort does not match the authorized Readiness cohort."
            ),
        }
        summary["liveExtractionAttemptsObserved"] = None
        _emit(summary, json_output=args.json)
        return 1

    post_budget = (
        max(1, 3 - post_existing_run.attempted_calls)
        if post_existing_run.attempted_calls < 3
        else 1
    )
    post_readiness, reassessed_run = _assess_readiness(
        preflight=preflight,
        reviewer=reviewer,
        title=title,
        max_new_extractions=post_budget,
        web_base_url=args.web_base_url,
        settings=settings,
    )
    if reassessed_run is not None:
        post_existing_run = reassessed_run
    new_evidence = _new_attempt_evidence(post_existing_run, before_counts)
    live_attempts_observed = sum(item["attemptDelta"] for item in new_evidence)
    missing_trace_case_ids = [
        item["caseId"] for item in new_evidence if item["traceRunId"] is None
    ]
    attempt_budget_exceeded = (
        live_attempts_observed > args.max_new_extractions
    )

    post_command = None
    if post_readiness.provider_execution_allowed:
        post_command = _operator_command_preview(
            dataset=dataset_path,
            reviewer=reviewer,
            title=title,
            max_new_extractions=post_budget,
            private_root=private_root,
            session_manifest=manifest_path,
        )
    try:
        _write_manifest(
            path=manifest_path,
            private_root=private_root,
            readiness=post_readiness,
            existing_run=post_existing_run,
            dataset=dataset_path,
            recommended_command=post_command,
        )
        summary["sessionManifestPath"] = str(manifest_path)
        summary["sessionManifestUpdatedAfterExecution"] = True
    except (OSError, RequirementAcceptanceCanaryOperatorError) as error:
        summary["postExecutionManifestError"] = type(error).__name__

    dataset_file_sha256_after = file_sha256(dataset_path)
    dataset_byte_count_after = dataset_path.stat().st_size
    dataset_changed = (
        dataset_file_sha256_after != dataset_file_sha256_before
        or dataset_byte_count_after != dataset_byte_count_before
    )
    summary["datasetFileChangedDuringExecution"] = dataset_changed
    summary["datasetFileSha256AfterExecution"] = dataset_file_sha256_after
    summary["datasetByteCountAfterExecution"] = dataset_byte_count_after
    summary["postReadiness"] = readiness_summary(
        post_readiness,
        recommended_command=post_command,
        session_manifest_path=(
            str(manifest_path)
            if summary["sessionManifestUpdatedAfterExecution"]
            else None
        ),
    )
    summary["newAttemptEvidence"] = new_evidence
    summary["liveExtractionAttemptsObserved"] = live_attempts_observed
    summary["missingTraceCaseIds"] = missing_trace_case_ids
    summary["attemptBudgetExceeded"] = attempt_budget_exceeded
    summary["workbenchUrl"] = post_readiness.workbench_url
    summary["manualHumanDecisionRequired"] = (
        post_readiness.next_action
        is RequirementAcceptanceReadinessNextAction.REVIEW_CANARY
    )
    if live_attempts_observed == 0:
        summary["executionOutcome"] = "no_new_live_attempts_observed"
    elif (
        preparation.failed_extractions
        or missing_trace_case_ids
        or attempt_budget_exceeded
        or post_readiness.next_action
        is RequirementAcceptanceReadinessNextAction.FIX_BLOCKERS
        or dataset_changed
        or summary.get("postExecutionManifestError") is not None
    ):
        summary["executionOutcome"] = "completed_with_attention_required"
    else:
        summary["executionOutcome"] = "completed"

    _emit(summary, json_output=args.json)
    return 0 if summary["executionOutcome"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
