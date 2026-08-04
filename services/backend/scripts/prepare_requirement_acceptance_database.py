"""Safely prepare the local SQLite schema for live Requirement acceptance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy.exc import SQLAlchemyError

from app.application.requirement_acceptance.database_checkpoint import (
    DATABASE_CHECKPOINT_SCHEMA_VERSION,
    database_checkpoint_receipt_path,
    load_database_checkpoint_receipt,
    mark_database_checkpoint_already_at_head,
    mark_database_checkpoint_applied,
    mark_database_checkpoint_backup_verified,
    mark_database_checkpoint_failed,
    mark_database_checkpoint_migration_attempted,
    new_database_checkpoint_receipt,
    requirement_acceptance_database_checkpoint_id,
    validate_database_checkpoint_identity,
    verify_database_checkpoint_backup,
)
from app.application.requirement_acceptance.local_bootstrap import (
    RequirementAcceptanceBootstrapError,
    backup_sqlite_database,
    planned_backup_path,
    sqlite_database_path,
    sqlite_integrity_check,
)
from app.application.requirement_acceptance.session_manifest import (
    write_requirement_acceptance_session_manifest,
)
from app.core.config import get_settings
from scripts.check_requirement_acceptance_readiness import (
    BACKEND_ROOT,
    _database_revision,
    _migration_head,
)

PROJECT_ROOT = BACKEND_ROOT.parents[1]
PRIVATE_DATA_ROOT = (PROJECT_ROOT / "data" / "private").resolve()
DEFAULT_PRIVATE_ROOT = PRIVATE_DATA_ROOT / "requirement-acceptance"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-root",
        type=Path,
        default=DEFAULT_PRIVATE_ROOT,
        help="Git-ignored root for backup and checkpoint evidence.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create/reuse a verified backup and migrate SQLite to Alembic head.",
    )
    parser.add_argument(
        "--confirm-backend-stopped",
        action="store_true",
        help="Required with --apply when a migration is pending.",
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


def _write_checkpoint_receipt(
    path: Path,
    receipt: dict[str, Any],
    *,
    private_root: Path,
) -> None:
    resolved = path.resolve()
    if not resolved.is_relative_to(private_root.resolve()):
        raise RequirementAcceptanceBootstrapError(
            "Database checkpoint receipt escapes the configured private root."
        )
    write_requirement_acceptance_session_manifest(resolved, receipt)


def _emit(summary: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print(
        "Requirement acceptance database checkpoint "
        f"state={summary['state']} applyExecuted={summary['applyExecuted']} "
        "providerCalls=0 acceptanceDomainWrites=0"
    )
    if summary.get("backupPath"):
        print(f"Backup: {summary['backupPath']}")
    print(f"Receipt: {summary['receiptPath']}")
    for blocker in summary.get("blockers", []):
        print(f"- blocker: {blocker}")


def _receipt_summary(
    receipt: dict[str, Any],
    *,
    current_revision: str | None,
    migration_head: str,
    receipt_path: Path,
    apply_executed: bool,
    backup_reused: bool,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    backup = receipt.get("backup") if isinstance(receipt.get("backup"), dict) else None
    migration = (
        receipt.get("migration")
        if isinstance(receipt.get("migration"), dict)
        else {}
    )
    return {
        "schemaVersion": DATABASE_CHECKPOINT_SCHEMA_VERSION,
        "checkpointId": receipt["checkpointId"],
        "state": receipt["state"],
        "databasePath": receipt["databasePath"],
        "sourceRevision": receipt.get("sourceRevision"),
        "currentRevision": current_revision,
        "targetRevision": migration_head,
        "migrationNeeded": current_revision != migration_head,
        "applyExecuted": apply_executed,
        "backupPath": backup.get("path") if backup else None,
        "backupVerified": bool(backup and backup.get("fileSha256")),
        "backupReused": backup_reused,
        "migrationAttempted": bool(migration.get("attempted")),
        "migrationApplied": bool(migration.get("applied")),
        "recoveredAfterCrash": bool(migration.get("recoveredAfterCrash")),
        "integrityAfter": migration.get("integrityAfter"),
        "receiptPath": str(receipt_path.resolve()),
        "blockers": blockers or [],
        "providerCalls": 0,
        "acceptanceDomainWrites": 0,
    }


def main() -> int:
    args = _arguments()
    private_root = args.private_root.resolve()
    if not private_root.is_relative_to(PRIVATE_DATA_ROOT):
        print(
            "Database checkpoint rejected: --private-root must stay under "
            f"{PRIVATE_DATA_ROOT}"
        )
        return 2

    settings = get_settings()
    try:
        database_path = sqlite_database_path(
            settings.database_url,
            backend_root=BACKEND_ROOT,
        )
    except RequirementAcceptanceBootstrapError as error:
        print(f"Database checkpoint rejected: {error}")
        return 2

    migration_head = _migration_head()
    database_reachable, current_revision, database_error = _database_revision(
        settings.database_url
    )
    if not database_reachable:
        print(
            "Database checkpoint rejected: "
            f"{database_error or 'database is not readable'}"
        )
        return 2

    checkpoint_id = requirement_acceptance_database_checkpoint_id(
        database_path=database_path,
        migration_head=migration_head,
    )
    receipt_path = database_checkpoint_receipt_path(
        private_root=private_root,
        checkpoint_id=checkpoint_id,
    ).resolve()
    if not receipt_path.is_relative_to(private_root):
        print("Database checkpoint rejected: receipt path escapes private root")
        return 2

    try:
        receipt = load_database_checkpoint_receipt(receipt_path)
        if receipt is not None:
            validate_database_checkpoint_identity(
                receipt,
                checkpoint_id=checkpoint_id,
                database_path=database_path,
                migration_head=migration_head,
            )
    except RequirementAcceptanceBootstrapError as error:
        print(f"Database checkpoint rejected: {error}")
        return 2

    if receipt is None:
        backup_path = (
            planned_backup_path(
                private_root=private_root,
                database_path=database_path,
                database_revision=current_revision,
            )
            if current_revision != migration_head
            else None
        )
        receipt = new_database_checkpoint_receipt(
            checkpoint_id=checkpoint_id,
            database_path=database_path,
            source_revision=current_revision,
            migration_head=migration_head,
            backup_path=backup_path,
        )

    source_revision = receipt.get("sourceRevision")
    if current_revision not in {source_revision, migration_head}:
        summary = _receipt_summary(
            receipt,
            current_revision=current_revision,
            migration_head=migration_head,
            receipt_path=receipt_path,
            apply_executed=args.apply,
            backup_reused=False,
            blockers=[
                "Database revision no longer matches the checkpoint source or target; "
                "inspect the verified backup and database before continuing."
            ],
        )
        _emit(summary, json_output=args.json)
        return 2

    checkpoint_state = str(receipt.get("state") or "planned")
    migration_evidence = (
        receipt.get("migration")
        if isinstance(receipt.get("migration"), dict)
        else {}
    )
    previous_migration_attempted = bool(migration_evidence.get("attempted"))
    state_blockers: list[str] = []
    if current_revision != migration_head:
        if checkpoint_state == "migration_attempted" or (
            checkpoint_state == "failed" and previous_migration_attempted
        ):
            state_blockers.append(
                "A previous migration attempt is inconclusive. Do not retry automatically; "
                "inspect the database and verified backup, then restore or repair explicitly."
            )
        elif checkpoint_state == "applied":
            state_blockers.append(
                "The database is behind a checkpoint already marked applied; inspect drift "
                "before any further migration."
            )

    if not args.apply or state_blockers:
        summary = _receipt_summary(
            receipt,
            current_revision=current_revision,
            migration_head=migration_head,
            receipt_path=receipt_path,
            apply_executed=args.apply,
            backup_reused=False,
            blockers=state_blockers,
        )
        _emit(summary, json_output=args.json)
        return 2 if state_blockers else 0

    if current_revision != migration_head and not args.confirm_backend_stopped:
        summary = _receipt_summary(
            receipt,
            current_revision=current_revision,
            migration_head=migration_head,
            receipt_path=receipt_path,
            apply_executed=True,
            backup_reused=False,
            blockers=[
                "Pending SQLite migration requires --confirm-backend-stopped."
            ],
        )
        _emit(summary, json_output=args.json)
        return 2

    backup_reused = False
    try:
        if current_revision == migration_head:
            integrity = sqlite_integrity_check(database_path)
            recovered = receipt.get("state") in {
                "backup_verified",
                "migration_attempted",
                "failed",
            }
            if recovered:
                backup = verify_database_checkpoint_backup(
                    receipt,
                    allowed_root=private_root,
                )
                del backup
                receipt = mark_database_checkpoint_applied(
                    receipt,
                    revision_after=migration_head,
                    integrity_after=integrity,
                    recovered_after_crash=True,
                )
            elif receipt.get("state") != "applied":
                receipt = mark_database_checkpoint_already_at_head(
                    receipt,
                    revision_after=migration_head,
                    integrity_after=integrity,
                )
            _write_checkpoint_receipt(
                receipt_path,
                receipt,
                private_root=private_root,
            )
            summary = _receipt_summary(
                receipt,
                current_revision=migration_head,
                migration_head=migration_head,
                receipt_path=receipt_path,
                apply_executed=True,
                backup_reused=recovered,
            )
            _emit(summary, json_output=args.json)
            return 0

        can_reuse_verified_backup = receipt.get("state") == "backup_verified" or (
            receipt.get("state") == "failed" and not previous_migration_attempted
        )
        if can_reuse_verified_backup:
            verify_database_checkpoint_backup(receipt, allowed_root=private_root)
            backup_reused = True
        else:
            backup = receipt.get("backup")
            if not isinstance(backup, dict) or not isinstance(backup.get("path"), str):
                raise RequirementAcceptanceBootstrapError(
                    "Database checkpoint has no planned backup path."
                )
            backup_result = backup_sqlite_database(
                database_path,
                Path(backup["path"]),
                allowed_root=private_root,
            )
            receipt = mark_database_checkpoint_backup_verified(
                receipt,
                backup_path=backup_result.backup_path,
                file_sha256_value=backup_result.file_sha256,
                byte_count=backup_result.byte_count,
                integrity_check=backup_result.integrity_check,
                source_revision=backup_result.source_revision,
            )
            _write_checkpoint_receipt(
                receipt_path,
                receipt,
                private_root=private_root,
            )

        receipt = mark_database_checkpoint_migration_attempted(receipt)
        _write_checkpoint_receipt(
            receipt_path,
            receipt,
            private_root=private_root,
        )
        _upgrade_database_to_head()
        reachable_after, revision_after, error_after = _database_revision(
            settings.database_url
        )
        if not reachable_after or revision_after != migration_head:
            raise RequirementAcceptanceBootstrapError(
                "Database verification after migration failed: "
                f"revision={revision_after!r}, expected={migration_head!r}, "
                f"error={error_after or 'none'}"
            )
        integrity_after = sqlite_integrity_check(database_path)
        receipt = mark_database_checkpoint_applied(
            receipt,
            revision_after=migration_head,
            integrity_after=integrity_after,
            recovered_after_crash=False,
        )
        _write_checkpoint_receipt(
            receipt_path,
            receipt,
            private_root=private_root,
        )
    except (OSError, RequirementAcceptanceBootstrapError) as error:
        _, revision_after, _ = _database_revision(settings.database_url)
        receipt = mark_database_checkpoint_failed(
            receipt,
            error=error,
            revision_after=revision_after,
        )
        try:
            _write_checkpoint_receipt(
                receipt_path,
                receipt,
                private_root=private_root,
            )
        except (OSError, RequirementAcceptanceBootstrapError):
            pass
        summary = _receipt_summary(
            receipt,
            current_revision=revision_after,
            migration_head=migration_head,
            receipt_path=receipt_path,
            apply_executed=True,
            backup_reused=backup_reused,
            blockers=[str(error)],
        )
        _emit(summary, json_output=args.json)
        return 2

    summary = _receipt_summary(
        receipt,
        current_revision=migration_head,
        migration_head=migration_head,
        receipt_path=receipt_path,
        apply_executed=True,
        backup_reused=backup_reused,
    )
    _emit(summary, json_output=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
