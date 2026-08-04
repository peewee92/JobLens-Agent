"""Check whether the next live Requirement acceptance action is safe and reproducible."""
from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.application.requirement_acceptance import (
    InvalidRequirementAcceptanceDatasetError,
    preflight_requirement_acceptance_dataset,
)
from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessNextAction,
    evaluate_requirement_acceptance_readiness,
)
from app.application.requirement_acceptance.runtime_environment import (
    read_requirement_acceptance_database_revision,
    requirement_acceptance_migration_head,
)
from app.application.requirement_acceptance.runs import (
    RequirementAcceptanceCanaryDecision,
    RequirementAcceptanceRunDetail,
)
from app.application.requirement_acceptance.session_manifest import (
    build_requirement_acceptance_session_manifest,
    write_requirement_acceptance_session_manifest,
)
from app.core.config import get_settings
from app.repositories import SqlAlchemyRequirementAcceptanceRunQueryRepository
from app.workflows.job_requirement_extraction import EXTRACTOR_VERSION, PROMPT_VERSION

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--title")
    parser.add_argument("--max-new-extractions", type=int)
    parser.add_argument("--web-base-url", default="http://localhost:3000")
    parser.add_argument(
        "--session-manifest",
        type=Path,
        help="Atomically write a secret-free JSON execution/evidence manifest.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InvalidRequirementAcceptanceDatasetError(
            f"Dataset file was not found: {path}"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise InvalidRequirementAcceptanceDatasetError(
            f"Dataset file could not be read as JSON: {type(error).__name__}"
        ) from error
    if not isinstance(payload, dict):
        raise InvalidRequirementAcceptanceDatasetError(
            "Dataset root must be a JSON object"
        )
    return payload


def _default_title(payload: dict[str, Any], path: Path) -> str:
    generated_at = payload.get("generatedAt")
    if isinstance(generated_at, str) and generated_at.strip():
        return f"Requirement acceptance {generated_at.strip()}"
    return f"Requirement acceptance {path.stem}"


def _migration_head() -> str:
    return requirement_acceptance_migration_head(backend_root=BACKEND_ROOT)


def _database_revision(database_url: str) -> tuple[bool, str | None, str | None]:
    return read_requirement_acceptance_database_revision(
        database_url,
        backend_root=BACKEND_ROOT,
    )


def _existing_run(
    *,
    dataset_fingerprint: str,
    title: str,
    reviewer: str,
    provider: str,
    model: str,
):
    from app.db.session import SessionLocal

    repository = SqlAlchemyRequirementAcceptanceRunQueryRepository(SessionLocal)
    return repository.get_by_identity(
        dataset_fingerprint=dataset_fingerprint,
        title=title,
        reviewer=reviewer,
        provider=provider,
        model=model,
        extractor_version=EXTRACTOR_VERSION,
        prompt_version=PROMPT_VERSION,
    )


def _command_preview(
    *,
    dataset: Path,
    reviewer: str,
    title: str,
    max_new_extractions: int,
    next_action: RequirementAcceptanceReadinessNextAction,
    existing_run: RequirementAcceptanceRunDetail | None,
) -> str | None:
    command = [
        ".venv/bin/python",
        "-m",
    ]
    if next_action is RequirementAcceptanceReadinessNextAction.RUN_CANARY:
        command.append("scripts.operate_requirement_acceptance_canary")
    elif (
        next_action is RequirementAcceptanceReadinessNextAction.RESUME_RUN
        and existing_run is not None
        and existing_run.canary_review is not None
        and existing_run.canary_review.decision
        is RequirementAcceptanceCanaryDecision.CONTINUE
    ):
        command.extend(
            [
                "scripts.operate_requirement_acceptance_resume",
                str(dataset.resolve()),
                "--reviewer",
                reviewer,
                "--title",
                title,
                "--max-new-extractions",
                str(max_new_extractions),
                "--expected-run-id",
                existing_run.id,
                "--expected-canary-review-id",
                existing_run.canary_review.id,
                "--json",
            ]
        )
        return shlex.join(command)
    else:
        return None

    command.extend(
        [
            str(dataset.resolve()),
            "--reviewer",
            reviewer,
            "--title",
            title,
            "--max-new-extractions",
            str(max_new_extractions),
            "--json",
        ]
    )
    return shlex.join(command)


def _summary(
    result,
    *,
    recommended_command: str | None,
    session_id: str | None = None,
    session_manifest_path: str | None = None,
) -> dict[str, Any]:
    return {
        "datasetFingerprint": result.dataset_fingerprint,
        "sourceVersion": result.source_version,
        "selectedCount": result.selected_count,
        "provider": result.provider,
        "model": result.model,
        "apiKeyConfigured": result.api_key_configured,
        "reviewer": result.reviewer,
        "title": result.title,
        "requestedMaxNewExtractions": result.requested_max_new_extractions,
        "databaseReachable": result.database_reachable,
        "databaseRevision": result.database_revision,
        "migrationHead": result.migration_head,
        "workflowReady": result.workflow_ready,
        "providerExecutionAllowed": result.provider_execution_allowed,
        "readyForNextAction": result.ready_for_next_action,
        "nextAction": result.next_action.value,
        "runId": result.run_id,
        "runStatus": result.run_status,
        "attemptedCalls": result.attempted_calls,
        "canaryDecision": (
            result.canary_decision.value if result.canary_decision is not None else None
        ),
        "batchId": result.batch_id,
        "workbenchUrl": result.workbench_url,
        "manualReviewUrl": result.manual_review_url,
        "recommendedCommand": recommended_command,
        "sessionId": session_id,
        "sessionManifestPath": session_manifest_path,
        "blockers": [
            {
                "scope": blocker.scope.value,
                "code": blocker.code,
                "message": blocker.message,
            }
            for blocker in result.blockers
        ],
        "dbWrites": 0,
        "providerCalls": 0,
    }


def main() -> int:
    args = _arguments()
    try:
        payload = _load_payload(args.dataset)
        preflight = preflight_requirement_acceptance_dataset(payload)
    except InvalidRequirementAcceptanceDatasetError as error:
        print(f"Readiness rejected: {error}")
        return 2

    settings = get_settings()
    provider = settings.requirement_extractor_provider.strip().casefold() or "disabled"
    model = settings.requirement_extractor_model.strip()
    title = (args.title or _default_title(payload, args.dataset)).strip()
    reviewer = args.reviewer.strip()
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

    result = evaluate_requirement_acceptance_readiness(
        preflight=preflight,
        provider=provider,
        model=model,
        api_key_configured=bool(
            settings.openai_api_key and settings.openai_api_key.strip()
        ),
        reviewer=reviewer,
        title=title,
        max_new_extractions=args.max_new_extractions,
        database_reachable=database_reachable,
        database_revision=database_revision,
        migration_head=head,
        existing_run=existing_run,
        web_base_url=args.web_base_url,
        database_error=database_error,
    )
    recommended_command = None
    if (
        result.provider_execution_allowed
        and args.max_new_extractions is not None
    ):
        recommended_command = _command_preview(
            dataset=args.dataset,
            reviewer=result.reviewer,
            title=result.title,
            max_new_extractions=args.max_new_extractions,
            next_action=result.next_action,
            existing_run=existing_run,
        )
    session_id = None
    session_manifest_path = None
    if args.session_manifest is not None:
        manifest = build_requirement_acceptance_session_manifest(
            readiness=result,
            existing_run=existing_run,
            dataset_path=args.dataset,
            extractor_version=EXTRACTOR_VERSION,
            prompt_version=PROMPT_VERSION,
            recommended_command=recommended_command,
        )
        try:
            write_requirement_acceptance_session_manifest(
                args.session_manifest,
                manifest,
            )
        except OSError as error:
            print(
                "Readiness manifest could not be written: "
                f"{type(error).__name__}"
            )
            return 2
        session_id = str(manifest["sessionId"])
        session_manifest_path = str(args.session_manifest.resolve())

    summary = _summary(
        result,
        recommended_command=recommended_command,
        session_id=session_id,
        session_manifest_path=session_manifest_path,
    )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            "Requirement acceptance readiness "
            f"nextAction={result.next_action.value} "
            f"workflowReady={result.workflow_ready} "
            f"providerExecutionAllowed={result.provider_execution_allowed} "
            "dbWrites=0 providerCalls=0"
        )
        for blocker in result.blockers:
            print(f"- [{blocker.scope.value}] {blocker.code}: {blocker.message}")
        if result.workbench_url:
            print(f"Workbench: {result.workbench_url}")
        if result.manual_review_url:
            print(f"Manual review: {result.manual_review_url}")
        if recommended_command:
            print(f"Command: {recommended_command}")
        if session_manifest_path:
            print(f"Session manifest: {session_manifest_path}")

    return 0 if result.ready_for_next_action else 1


if __name__ == "__main__":
    raise SystemExit(main())
