"""Safely prepare local files and SQLite schema for live Requirement acceptance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy.exc import SQLAlchemyError

from app.application.requirement_acceptance import (
    InvalidRequirementAcceptanceDatasetError,
    preflight_requirement_acceptance_dataset,
)
from app.application.requirement_acceptance.local_bootstrap import (
    RequirementAcceptanceBootstrapError,
    backup_sqlite_database,
    build_requirement_acceptance_bootstrap_plan,
    sqlite_integrity_check,
    stage_private_dataset,
)
from app.application.requirement_acceptance.readiness import (
    evaluate_requirement_acceptance_readiness,
)
from app.application.requirement_acceptance.session_manifest import (
    write_requirement_acceptance_session_manifest,
)
from app.core.config import get_settings
from app.workflows.job_requirement_extraction import EXTRACTOR_VERSION, PROMPT_VERSION
from scripts.check_requirement_acceptance_readiness import (
    BACKEND_ROOT,
    _command_preview,
    _database_revision,
    _default_title,
    _existing_run,
    _load_payload,
    _migration_head,
    _summary as readiness_summary,
)

PROJECT_ROOT = BACKEND_ROOT.parents[1]
PRIVATE_DATA_ROOT = (PROJECT_ROOT / "data" / "private").resolve()
DEFAULT_PRIVATE_ROOT = PRIVATE_DATA_ROOT / "requirement-acceptance"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--title")
    parser.add_argument("--max-new-extractions", type=int)
    parser.add_argument("--web-base-url", default="http://localhost:3000")
    parser.add_argument(
        "--private-root",
        type=Path,
        default=DEFAULT_PRIVATE_ROOT,
        help="Git-ignored local root for staged datasets and SQLite backups.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Stage the dataset, back up SQLite and apply pending migrations.",
    )
    parser.add_argument(
        "--confirm-backend-stopped",
        action="store_true",
        help="Required with --apply so SQLite migration is not run beside the app.",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Atomically write the secret-free bootstrap result as JSON.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


def _upgrade_database_to_head() -> None:
    try:
        command.upgrade(_alembic_config(), "head")
    except (CommandError, SQLAlchemyError, OSError) as error:
        raise RequirementAcceptanceBootstrapError(
            f"Alembic upgrade failed: {type(error).__name__}"
        ) from error


def _serialize_path(path: Path | None) -> str | None:
    return str(path.resolve()) if path is not None else None


def _plan_summary(plan) -> dict[str, Any]:
    return {
        "dataset": {
            "sourcePath": _serialize_path(plan.dataset_source_path),
            "destinationPath": _serialize_path(plan.dataset_destination_path),
            "fileSha256": plan.dataset_file_sha256,
            "byteCount": plan.dataset_byte_count,
            "stageNeeded": plan.dataset_stage_needed,
        },
        "database": {
            "path": _serialize_path(plan.database_path),
            "revisionBefore": plan.database_revision,
            "migrationHead": plan.migration_head,
            "migrationNeeded": plan.migration_needed,
            "plannedBackupPath": _serialize_path(plan.planned_backup_path),
        },
        "applyAllowed": plan.apply_allowed,
        "blockers": list(plan.blockers),
    }


def _readiness_after_bootstrap(
    *,
    dataset_path: Path,
    preflight,
    reviewer: str,
    title: str,
    max_new_extractions: int | None,
    web_base_url: str,
    settings,
    migration_head: str,
) -> dict[str, Any]:
    provider = settings.requirement_extractor_provider.strip().casefold() or "disabled"
    model = settings.requirement_extractor_model.strip()
    database_reachable, database_revision, database_error = _database_revision(
        settings.database_url
    )
    existing_run = None
    if (
        database_reachable
        and database_revision == migration_head
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
        max_new_extractions=max_new_extractions,
        database_reachable=database_reachable,
        database_revision=database_revision,
        migration_head=migration_head,
        existing_run=existing_run,
        web_base_url=web_base_url,
        database_error=database_error,
    )
    recommended_command = None
    if result.provider_execution_allowed and max_new_extractions is not None:
        recommended_command = _command_preview(
            dataset=dataset_path,
            reviewer=reviewer,
            title=title,
            max_new_extractions=max_new_extractions,
            next_action=result.next_action,
            existing_run=existing_run,
        )
    return readiness_summary(
        result,
        recommended_command=recommended_command,
    )


def _write_receipt(
    summary: dict[str, Any],
    receipt_path: Path | None,
    *,
    private_root: Path,
) -> bool:
    if receipt_path is None:
        return True
    if not receipt_path.resolve().is_relative_to(private_root.resolve()):
        summary["outputWrites"]["receiptError"] = "private_root_escape"
        return False
    summary["outputWrites"]["receiptWritten"] = True
    try:
        write_requirement_acceptance_session_manifest(receipt_path, summary)
    except OSError as error:
        summary["outputWrites"]["receiptWritten"] = False
        summary["outputWrites"]["receiptError"] = type(error).__name__
        return False
    return True


def _emit(summary: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print(
        "Requirement acceptance local bootstrap "
        f"mode={summary['mode']} localPreparationSucceeded="
        f"{summary['localPreparationSucceeded']} providerCalls=0"
    )
    for blocker in summary["plan"]["blockers"]:
        print(f"- blocker: {blocker}")
    database = summary["plan"]["database"]
    if database["migrationNeeded"]:
        print(f"Database backup: {database['plannedBackupPath']}")
    readiness = summary.get("readiness")
    if readiness is not None:
        print(
            f"Readiness: nextAction={readiness['nextAction']} "
            f"providerExecutionAllowed={readiness['providerExecutionAllowed']}"
        )


def main() -> int:
    args = _arguments()
    try:
        payload = _load_payload(args.dataset)
        preflight = preflight_requirement_acceptance_dataset(payload)
    except InvalidRequirementAcceptanceDatasetError as error:
        print(f"Bootstrap rejected: {error}")
        return 2

    private_root = args.private_root.resolve()
    if not private_root.is_relative_to(PRIVATE_DATA_ROOT):
        print(
            "Bootstrap rejected: --private-root must stay under the Git-ignored "
            f"directory {PRIVATE_DATA_ROOT}"
        )
        return 2

    if args.receipt is not None and not args.receipt.resolve().is_relative_to(
        private_root
    ):
        print(
            "Bootstrap rejected: --receipt must stay under the selected "
            f"private root {private_root}"
        )
        return 2

    settings = get_settings()
    reviewer = args.reviewer.strip()
    title = (args.title or _default_title(payload, args.dataset)).strip()
    migration_head = _migration_head()
    database_reachable, database_revision, database_error = _database_revision(
        settings.database_url
    )
    try:
        plan = build_requirement_acceptance_bootstrap_plan(
            dataset_source_path=args.dataset,
            dataset_fingerprint=preflight.dataset_fingerprint,
            private_root=private_root,
            database_url=settings.database_url,
            backend_root=BACKEND_ROOT,
            database_revision=database_revision,
            migration_head=migration_head,
            database_reachable=database_reachable,
            database_error=database_error,
        )
    except RequirementAcceptanceBootstrapError as error:
        print(f"Bootstrap rejected: {error}")
        return 2

    summary: dict[str, Any] = {
        "mode": "apply" if args.apply else "plan",
        "planValidated": plan.apply_allowed,
        "applyExecuted": args.apply,
        "localPreparationSucceeded": False,
        "plan": _plan_summary(plan),
        "mutations": {
            "datasetStaged": False,
            "databaseBackupCreated": False,
            "migrationAttempted": False,
            "migrationApplied": False,
        },
        "datasetStage": None,
        "databaseBackup": None,
        "databaseRevisionAfter": database_revision,
        "databaseIntegrityAfter": None,
        "readiness": None,
        "providerCalls": 0,
        "acceptanceDomainWrites": 0,
        "outputWrites": {
            "receiptRequested": args.receipt is not None,
            "receiptPath": _serialize_path(args.receipt),
            "receiptWritten": False,
            "receiptError": None,
        },
    }

    if not plan.apply_allowed:
        _emit(summary, json_output=args.json)
        return 2

    if not args.apply:
        if not _write_receipt(
            summary,
            args.receipt,
            private_root=private_root,
        ):
            _emit(summary, json_output=args.json)
            return 2
        _emit(summary, json_output=args.json)
        return 0

    if plan.migration_needed and not args.confirm_backend_stopped:
        summary["plan"]["blockers"].append(
            "A pending SQLite migration requires --confirm-backend-stopped."
        )
        _emit(summary, json_output=args.json)
        return 2

    backup_result = None
    try:
        stage_result = stage_private_dataset(
            plan.dataset_source_path,
            plan.dataset_destination_path,
            allowed_root=private_root,
        )
        summary["mutations"]["datasetStaged"] = not stage_result.reused
        summary["datasetStage"] = {
            "destinationPath": _serialize_path(stage_result.destination_path),
            "fileSha256": stage_result.file_sha256,
            "byteCount": stage_result.byte_count,
            "reused": stage_result.reused,
        }

        if plan.migration_needed:
            if plan.planned_backup_path is None:  # defensive plan invariant
                raise RequirementAcceptanceBootstrapError(
                    "Migration requires a planned SQLite backup path."
                )
            backup_result = backup_sqlite_database(
                plan.database_path,
                plan.planned_backup_path,
                allowed_root=private_root,
            )
            summary["mutations"]["databaseBackupCreated"] = True
            summary["databaseBackup"] = {
                "path": _serialize_path(backup_result.backup_path),
                "fileSha256": backup_result.file_sha256,
                "byteCount": backup_result.byte_count,
                "integrityCheck": backup_result.integrity_check,
                "sourceRevision": backup_result.source_revision,
            }
            summary["mutations"]["migrationAttempted"] = True
            _upgrade_database_to_head()
            summary["mutations"]["migrationApplied"] = True

        reachable_after, revision_after, error_after = _database_revision(
            settings.database_url
        )
        if not reachable_after or revision_after != migration_head:
            raise RequirementAcceptanceBootstrapError(
                "Database verification after migration failed: "
                f"revision={revision_after!r}, expected={migration_head!r}, "
                f"error={error_after or 'none'}"
            )
        integrity_after = sqlite_integrity_check(plan.database_path)
        summary["databaseRevisionAfter"] = revision_after
        summary["databaseIntegrityAfter"] = integrity_after
        summary["readiness"] = _readiness_after_bootstrap(
            dataset_path=plan.dataset_destination_path,
            preflight=preflight,
            reviewer=reviewer,
            title=title,
            max_new_extractions=args.max_new_extractions,
            web_base_url=args.web_base_url,
            settings=settings,
            migration_head=migration_head,
        )
        summary["localPreparationSucceeded"] = True
    except (OSError, RequirementAcceptanceBootstrapError) as error:
        # The verified backup path is intentionally
        # retained for explicit operator recovery; the script never auto-restores.
        summary["failure"] = {
            "type": type(error).__name__,
            "message": str(error),
            "verifiedBackupPath": (
                _serialize_path(backup_result.backup_path)
                if backup_result is not None
                else None
            ),
        }
        _write_receipt(
            summary,
            args.receipt,
            private_root=private_root,
        )
        _emit(summary, json_output=args.json)
        return 2

    if not _write_receipt(
        summary,
        args.receipt,
        private_root=private_root,
    ):
        _emit(summary, json_output=args.json)
        return 2
    _emit(summary, json_output=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
