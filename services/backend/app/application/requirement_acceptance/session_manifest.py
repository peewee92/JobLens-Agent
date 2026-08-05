"""Privacy-bounded execution manifest for one Requirement acceptance session."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessNextAction,
    RequirementAcceptanceReadinessResult,
)
from app.application.requirement_acceptance.runs import (
    RequirementAcceptanceRunDetail,
)

SESSION_MANIFEST_SCHEMA_VERSION = "requirement-acceptance-session-v1"


def requirement_acceptance_session_id(
    *,
    dataset_fingerprint: str,
    reviewer: str,
    title: str,
    provider: str,
    model: str,
    extractor_version: str,
    prompt_version: str,
) -> str:
    """Return a stable identity for one frozen acceptance cohort.

    Generated timestamps and per-invocation budgets are deliberately excluded so
    repeated readiness checks and resumptions refer to the same logical session.
    """

    identity = {
        "datasetFingerprint": dataset_fingerprint,
        "reviewer": reviewer.strip(),
        "title": title.strip(),
        "provider": provider.strip().casefold(),
        "model": model.strip(),
        "extractorVersion": extractor_version.strip(),
        "promptVersion": prompt_version.strip(),
    }
    digest = sha256(
        json.dumps(
            identity,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return f"reqacceptsession_{digest[:32]}"


def build_requirement_acceptance_session_manifest(
    *,
    readiness: RequirementAcceptanceReadinessResult,
    existing_run: RequirementAcceptanceRunDetail | None,
    dataset_path: Path,
    extractor_version: str,
    prompt_version: str,
    recommended_command: str | None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a public-safe operational evidence manifest.

    The manifest intentionally contains references and hashes, not API secrets,
    full JD text, raw Trace output, or human note bodies.
    """

    if not readiness.dataset_fingerprint or not readiness.source_version:
        raise ValueError(
            "Requirement acceptance Session Manifest requires a validated formal "
            "dataset fingerprint and source version."
        )
    dataset_fingerprint = readiness.dataset_fingerprint

    now = generated_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    session_id = requirement_acceptance_session_id(
        dataset_fingerprint=dataset_fingerprint,
        reviewer=readiness.reviewer,
        title=readiness.title,
        provider=readiness.provider,
        model=readiness.model,
        extractor_version=extractor_version,
        prompt_version=prompt_version,
    )
    safe_recommended_command = (
        recommended_command if readiness.provider_execution_allowed else None
    )
    command_hash = (
        sha256(safe_recommended_command.encode("utf-8")).hexdigest()
        if safe_recommended_command is not None
        else None
    )

    cases = []
    if existing_run is not None:
        frozen_canary_ids = set(
            existing_run.canary_review.reviewed_case_ids
            if existing_run.canary_review is not None
            else ()
        )
        for case in existing_run.cases:
            cases.append(
                {
                    "caseId": case.id,
                    "caseIndex": case.case_index,
                    "jobId": case.job_id,
                    "status": case.status.value,
                    "attemptCount": case.attempt_count,
                    "descriptionHash": case.description_hash,
                    "descriptionIsCurrent": case.description_is_current,
                    "extractionId": case.extraction_id,
                    "traceRunId": case.trace_run_id,
                    "errorCode": case.error_code,
                    "isPendingCanaryReviewEvidence": (
                        existing_run.canary_review is None
                        and existing_run.batch_id is None
                        and case.was_attempted
                    ),
                    "isFrozenCanaryEvidence": case.id in frozen_canary_ids,
                }
            )

    canary_review = None
    if existing_run is not None and existing_run.canary_review is not None:
        review = existing_run.canary_review
        canary_review = {
            "reviewId": review.id,
            "decision": review.decision.value,
            "reviewer": review.reviewer,
            "reviewedCaseIds": list(review.reviewed_case_ids),
            "reviewedExtractionIds": list(review.reviewed_extraction_ids),
            "reviewedTraceRunIds": list(review.reviewed_trace_run_ids),
            "reviewedAt": review.reviewed_at.isoformat(),
            "notesSha256": sha256(review.notes.encode("utf-8")).hexdigest(),
            "notesCharacterCount": len(review.notes),
        }

    blocker_items = [
        {
            "scope": blocker.scope.value,
            "code": blocker.code,
            "message": blocker.message,
        }
        for blocker in readiness.blockers
    ]

    next_action = readiness.next_action
    manifest_state = _manifest_state(readiness)
    return {
        "schemaVersion": SESSION_MANIFEST_SCHEMA_VERSION,
        "sessionId": session_id,
        "generatedAt": now.isoformat(),
        "state": manifest_state,
        "identity": {
            "datasetFingerprint": dataset_fingerprint,
            "sourceVersion": readiness.source_version,
            "selectedCount": readiness.selected_count,
            "datasetFileName": dataset_path.name,
            "datasetPath": str(dataset_path.resolve()),
            "reviewer": readiness.reviewer,
            "title": readiness.title,
            "provider": readiness.provider,
            "model": readiness.model,
            "extractorVersion": extractor_version,
            "promptVersion": prompt_version,
        },
        "readiness": {
            "workflowReady": readiness.workflow_ready,
            "providerExecutionAllowed": readiness.provider_execution_allowed,
            "readyForNextAction": readiness.ready_for_next_action,
            "nextAction": next_action.value,
            "requestedMaxNewExtractions": readiness.requested_max_new_extractions,
            "databaseReachable": readiness.database_reachable,
            "databaseRevision": readiness.database_revision,
            "migrationHead": readiness.migration_head,
            "apiKeyConfigured": readiness.api_key_configured,
            "blockers": blocker_items,
        },
        "execution": {
            "recommendedCommand": safe_recommended_command,
            "recommendedCommandSha256": command_hash,
            "dbWritesDuringManifestExport": 0,
            "providerCallsDuringManifestExport": 0,
        },
        "evidence": {
            "runId": readiness.run_id,
            "runStatus": readiness.run_status,
            "attemptedCalls": readiness.attempted_calls,
            "batchId": readiness.batch_id,
            "workbenchUrl": readiness.workbench_url,
            "manualReviewUrl": readiness.manual_review_url,
            "canaryReview": canary_review,
            "cases": cases,
        },
        "completionChecklist": {
            "formalDatasetValidated": True,
            "databaseAtMigrationHead": (
                readiness.database_reachable
                and readiness.database_revision == readiness.migration_head
            ),
            "liveProviderConfigured": readiness.provider == "openai",
            "liveModelConfigured": bool(readiness.model),
            "apiKeyConfigured": readiness.api_key_configured,
            "canaryStarted": readiness.attempted_calls > 0,
            "canaryHumanDecisionRecorded": canary_review is not None,
            "allTwentyExtractionsReady": readiness.batch_id is not None,
            "manualReviewBatchCreated": readiness.batch_id is not None,
            "allTwentyHumanDecisionsCompleted": None,
            "modelQualityApproved": None,
            "matchPhaseAllowed": False,
        },
        "expectedEvidence": [
            "formal dataset fingerprint and source version",
            "database revision equal to Alembic head",
            "one to three initial live Trace IDs",
            "exact Extraction IDs for successful Canary cases",
            "one immutable human continue/stop decision",
            "twenty current same-cohort Extractions",
            "one exact Manual Review Batch",
            "twenty human case decisions and an explicit quality conclusion",
        ],
        "privacy": {
            "containsApiKey": False,
            "containsFullJobDescriptions": False,
            "containsRawTraceOutput": False,
            "containsHumanReviewNotes": False,
            "containsLocalDatasetPath": True,
            "publicPortfolioSafeWithoutPathRedaction": False,
        },
    }


def write_requirement_acceptance_session_manifest(
    output_path: Path,
    manifest: dict[str, Any],
) -> None:
    """Atomically write one manifest to avoid partial operational evidence."""

    resolved = output_path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=resolved.parent,
            prefix=f".{resolved.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        temporary_path.replace(resolved)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _manifest_state(readiness: RequirementAcceptanceReadinessResult) -> str:
    if readiness.next_action is RequirementAcceptanceReadinessNextAction.STOPPED:
        return "stopped"
    if readiness.next_action is RequirementAcceptanceReadinessNextAction.REVIEW_CANARY:
        return "awaiting_human_canary_review"
    if readiness.next_action is RequirementAcceptanceReadinessNextAction.OPEN_MANUAL_REVIEW:
        return "awaiting_twenty_case_review"
    if readiness.provider_execution_allowed:
        return "ready_for_provider_execution"
    return "blocked"
