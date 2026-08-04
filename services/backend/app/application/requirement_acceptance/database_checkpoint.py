"""Resumable local SQLite migration checkpoint for Requirement acceptance.

The checkpoint records operational evidence only. It never imports Jobs,
writes Requirement acceptance domain records, or calls an LLM Provider.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from app.application.requirement_acceptance.local_bootstrap import (
    RequirementAcceptanceBootstrapError,
    file_sha256,
    sqlite_integrity_check,
    sqlite_revision,
)

DATABASE_CHECKPOINT_SCHEMA_VERSION = (
    "requirement-acceptance-database-checkpoint/v1"
)


def _utc_timestamp(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def requirement_acceptance_database_checkpoint_id(
    *,
    database_path: Path,
    migration_head: str,
) -> str:
    identity = {
        "databasePath": str(database_path.resolve()),
        "migrationHead": migration_head.strip(),
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"reqacceptdb_{sha256(encoded).hexdigest()[:32]}"


def database_checkpoint_receipt_path(
    *,
    private_root: Path,
    checkpoint_id: str,
) -> Path:
    return private_root.resolve() / "database-checkpoints" / f"{checkpoint_id}.json"


def new_database_checkpoint_receipt(
    *,
    checkpoint_id: str,
    database_path: Path,
    source_revision: str | None,
    migration_head: str,
    backup_path: Path | None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = _utc_timestamp(generated_at)
    return {
        "schemaVersion": DATABASE_CHECKPOINT_SCHEMA_VERSION,
        "checkpointId": checkpoint_id,
        "state": "planned",
        "databasePath": str(database_path.resolve()),
        "sourceRevision": source_revision,
        "targetRevision": migration_head,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "backup": (
            {
                "path": str(backup_path.resolve()),
                "fileSha256": None,
                "byteCount": None,
                "integrityCheck": None,
                "sourceRevision": None,
                "verifiedAt": None,
            }
            if backup_path is not None
            else None
        ),
        "migration": {
            "attempted": False,
            "applied": False,
            "revisionAfter": source_revision,
            "integrityAfter": None,
            "recoveredAfterCrash": False,
        },
        "failure": None,
        "providerCalls": 0,
        "acceptanceDomainWrites": 0,
    }


def load_database_checkpoint_receipt(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RequirementAcceptanceBootstrapError(
            f"Database checkpoint receipt could not be read: {type(error).__name__}"
        ) from error
    if not isinstance(payload, dict):
        raise RequirementAcceptanceBootstrapError(
            "Database checkpoint receipt root must be a JSON object."
        )
    return payload


def validate_database_checkpoint_identity(
    receipt: dict[str, Any],
    *,
    checkpoint_id: str,
    database_path: Path,
    migration_head: str,
) -> None:
    expected = {
        "schemaVersion": DATABASE_CHECKPOINT_SCHEMA_VERSION,
        "checkpointId": checkpoint_id,
        "databasePath": str(database_path.resolve()),
        "targetRevision": migration_head,
    }
    mismatches = [
        key
        for key, expected_value in expected.items()
        if receipt.get(key) != expected_value
    ]
    if mismatches:
        raise RequirementAcceptanceBootstrapError(
            "Database checkpoint identity mismatch: " + ", ".join(mismatches)
        )
    allowed_states = {
        "planned",
        "backup_verified",
        "migration_attempted",
        "applied",
        "failed",
    }
    if receipt.get("state") not in allowed_states:
        raise RequirementAcceptanceBootstrapError(
            "Database checkpoint state is invalid."
        )


def mark_database_checkpoint_backup_verified(
    receipt: dict[str, Any],
    *,
    backup_path: Path,
    file_sha256_value: str,
    byte_count: int,
    integrity_check: str,
    source_revision: str | None,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    updated = dict(receipt)
    updated["state"] = "backup_verified"
    updated["updatedAt"] = _utc_timestamp(updated_at)
    updated["backup"] = {
        "path": str(backup_path.resolve()),
        "fileSha256": file_sha256_value,
        "byteCount": byte_count,
        "integrityCheck": integrity_check,
        "sourceRevision": source_revision,
        "verifiedAt": _utc_timestamp(updated_at),
    }
    updated["failure"] = None
    return updated


def mark_database_checkpoint_migration_attempted(
    receipt: dict[str, Any],
    *,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    updated = dict(receipt)
    migration = dict(updated.get("migration") or {})
    migration["attempted"] = True
    migration["applied"] = False
    updated["migration"] = migration
    updated["state"] = "migration_attempted"
    updated["updatedAt"] = _utc_timestamp(updated_at)
    updated["failure"] = None
    return updated


def mark_database_checkpoint_applied(
    receipt: dict[str, Any],
    *,
    revision_after: str,
    integrity_after: str,
    recovered_after_crash: bool,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    updated = dict(receipt)
    migration = dict(updated.get("migration") or {})
    migration.update(
        {
            "attempted": True,
            "applied": True,
            "revisionAfter": revision_after,
            "integrityAfter": integrity_after,
            "recoveredAfterCrash": recovered_after_crash,
        }
    )
    updated["migration"] = migration
    updated["state"] = "applied"
    updated["updatedAt"] = _utc_timestamp(updated_at)
    updated["failure"] = None
    return updated


def mark_database_checkpoint_already_at_head(
    receipt: dict[str, Any],
    *,
    revision_after: str,
    integrity_after: str,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    updated = dict(receipt)
    migration = dict(updated.get("migration") or {})
    migration.update(
        {
            "attempted": False,
            "applied": True,
            "revisionAfter": revision_after,
            "integrityAfter": integrity_after,
            "recoveredAfterCrash": False,
        }
    )
    updated["migration"] = migration
    updated["state"] = "applied"
    updated["updatedAt"] = _utc_timestamp(updated_at)
    updated["failure"] = None
    return updated


def mark_database_checkpoint_failed(
    receipt: dict[str, Any],
    *,
    error: BaseException,
    revision_after: str | None,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    updated = dict(receipt)
    updated["state"] = "failed"
    updated["updatedAt"] = _utc_timestamp(updated_at)
    updated["failure"] = {
        "type": type(error).__name__,
        "message": str(error),
        "revisionAfter": revision_after,
    }
    return updated


def verify_database_checkpoint_backup(
    receipt: dict[str, Any],
    *,
    allowed_root: Path,
) -> Path:
    backup = receipt.get("backup")
    if not isinstance(backup, dict):
        raise RequirementAcceptanceBootstrapError(
            "Database checkpoint has no verified backup evidence."
        )
    path_value = backup.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise RequirementAcceptanceBootstrapError(
            "Database checkpoint backup path is missing."
        )
    path = Path(path_value).resolve()
    if not path.is_relative_to(allowed_root.resolve()):
        raise RequirementAcceptanceBootstrapError(
            "Database checkpoint backup escapes the configured private root."
        )
    if not path.is_file():
        raise RequirementAcceptanceBootstrapError(
            f"Database checkpoint backup does not exist: {path}"
        )
    expected_hash = backup.get("fileSha256")
    if not isinstance(expected_hash, str) or file_sha256(path) != expected_hash:
        raise RequirementAcceptanceBootstrapError(
            "Database checkpoint backup SHA-256 verification failed."
        )
    expected_size = backup.get("byteCount")
    if not isinstance(expected_size, int) or path.stat().st_size != expected_size:
        raise RequirementAcceptanceBootstrapError(
            "Database checkpoint backup byte-count verification failed."
        )
    if sqlite_integrity_check(path) != "ok":  # defensive helper invariant
        raise RequirementAcceptanceBootstrapError(
            "Database checkpoint backup integrity verification failed."
        )
    expected_revision = backup.get("sourceRevision")
    if sqlite_revision(path) != expected_revision:
        raise RequirementAcceptanceBootstrapError(
            "Database checkpoint backup revision verification failed."
        )
    return path
