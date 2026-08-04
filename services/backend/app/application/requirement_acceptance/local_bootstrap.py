"""Guarded local bootstrap helpers for live Requirement acceptance.

This module prepares only local files and the SQLite schema. It never imports
Jobs, writes Requirement acceptance domain records, or calls an LLM Provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import BinaryIO

from sqlalchemy.engine import make_url


class RequirementAcceptanceBootstrapError(RuntimeError):
    """Raised when local bootstrap cannot continue safely."""


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceDatasetStageResult:
    source_path: Path
    destination_path: Path
    file_sha256: str
    byte_count: int
    reused: bool


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceDatabaseBackupResult:
    source_path: Path
    backup_path: Path
    file_sha256: str
    byte_count: int
    integrity_check: str
    source_revision: str | None


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceBootstrapPlan:
    dataset_source_path: Path
    dataset_destination_path: Path
    dataset_file_sha256: str
    dataset_byte_count: int
    dataset_stage_needed: bool
    database_path: Path
    database_revision: str | None
    migration_head: str
    migration_needed: bool
    planned_backup_path: Path | None
    apply_allowed: bool
    blockers: tuple[str, ...]


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_database_path(database_url: str, *, backend_root: Path) -> Path:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        raise RequirementAcceptanceBootstrapError(
            "Local live bootstrap currently supports SQLite only."
        )
    if not url.database or url.database == ":memory:":
        raise RequirementAcceptanceBootstrapError(
            "Local live bootstrap requires a persistent SQLite database file."
        )
    path = Path(url.database)
    if not path.is_absolute():
        path = (backend_root / path).resolve()
    return path


def private_dataset_path(
    *,
    private_root: Path,
    dataset_fingerprint: str,
) -> Path:
    return private_root / "datasets" / f"formal-{dataset_fingerprint[:16]}.json"


def planned_backup_path(
    *,
    private_root: Path,
    database_path: Path,
    database_revision: str | None,
    generated_at: datetime | None = None,
) -> Path:
    timestamp = (generated_at or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")
    revision = database_revision or "unknown"
    return (
        private_root
        / "backups"
        / f"{database_path.stem}-{timestamp}-{revision}{database_path.suffix or '.sqlite3'}"
    )


def build_requirement_acceptance_bootstrap_plan(
    *,
    dataset_source_path: Path,
    dataset_fingerprint: str,
    private_root: Path,
    database_url: str,
    backend_root: Path,
    database_revision: str | None,
    migration_head: str,
    database_reachable: bool,
    database_error: str | None = None,
    generated_at: datetime | None = None,
) -> RequirementAcceptanceBootstrapPlan:
    source = dataset_source_path.resolve()
    if not source.is_file():
        raise RequirementAcceptanceBootstrapError(
            f"Formal dataset file does not exist: {source}"
        )
    private_root_resolved = private_root.resolve()
    destination = private_dataset_path(
        private_root=private_root_resolved,
        dataset_fingerprint=dataset_fingerprint,
    ).resolve()
    source_hash = file_sha256(source)
    source_size = source.stat().st_size
    blockers: list[str] = []
    if not destination.is_relative_to(private_root_resolved):
        blockers.append(
            "Private dataset destination escapes the configured private root."
        )
    try:
        database_path = sqlite_database_path(
            database_url,
            backend_root=backend_root.resolve(),
        )
    except RequirementAcceptanceBootstrapError as error:
        database_path = backend_root.resolve() / "unsupported-database"
        blockers.append(str(error))

    if not database_reachable:
        blockers.append(
            database_error
            or "Configured SQLite database is not reachable for bootstrap."
        )
    elif not database_path.is_file():
        blockers.append(f"SQLite database file does not exist: {database_path}")

    if destination.exists() and file_sha256(destination) != source_hash:
        blockers.append(
            "Private dataset destination exists with different bytes; refuse to overwrite it."
        )
    stage_needed = not destination.exists()
    migration_needed = database_revision != migration_head
    backup = (
        planned_backup_path(
            private_root=private_root_resolved,
            database_path=database_path,
            database_revision=database_revision,
            generated_at=generated_at,
        )
        if migration_needed and database_reachable and database_path.is_file()
        else None
    )
    if backup is not None:
        backup = backup.resolve()
        if not backup.is_relative_to(private_root_resolved):
            blockers.append(
                "SQLite backup destination escapes the configured private root."
            )

    return RequirementAcceptanceBootstrapPlan(
        dataset_source_path=source,
        dataset_destination_path=destination,
        dataset_file_sha256=source_hash,
        dataset_byte_count=source_size,
        dataset_stage_needed=stage_needed,
        database_path=database_path,
        database_revision=database_revision,
        migration_head=migration_head,
        migration_needed=migration_needed,
        planned_backup_path=backup,
        apply_allowed=not blockers,
        blockers=tuple(blockers),
    )


def _copy_bytes(source: BinaryIO, destination: BinaryIO) -> None:
    while chunk := source.read(1024 * 1024):
        destination.write(chunk)


def stage_private_dataset(
    source_path: Path,
    destination_path: Path,
    *,
    allowed_root: Path | None = None,
) -> RequirementAcceptanceDatasetStageResult:
    source = source_path.resolve()
    destination = destination_path.resolve()
    if allowed_root is not None and not destination.is_relative_to(
        allowed_root.resolve()
    ):
        raise RequirementAcceptanceBootstrapError(
            "Private dataset destination escapes the configured private root at apply time."
        )
    expected_hash = file_sha256(source)
    expected_size = source.stat().st_size
    if destination.exists():
        actual_hash = file_sha256(destination)
        if actual_hash != expected_hash:
            raise RequirementAcceptanceBootstrapError(
                "Private dataset destination exists with different bytes."
            )
        return RequirementAcceptanceDatasetStageResult(
            source_path=source,
            destination_path=destination,
            file_sha256=actual_hash,
            byte_count=destination.stat().st_size,
            reused=True,
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with source.open("rb") as source_handle:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as destination_handle:
                temp_path = Path(destination_handle.name)
                _copy_bytes(source_handle, destination_handle)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
        copied_hash = file_sha256(temp_path)
        copied_size = temp_path.stat().st_size
        if copied_hash != expected_hash or copied_size != expected_size:
            raise RequirementAcceptanceBootstrapError(
                "Private dataset staging verification failed."
            )
        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return RequirementAcceptanceDatasetStageResult(
        source_path=source,
        destination_path=destination,
        file_sha256=expected_hash,
        byte_count=expected_size,
        reused=False,
    )


def sqlite_integrity_check(path: Path) -> str:
    try:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as error:
        raise RequirementAcceptanceBootstrapError(
            f"SQLite integrity check failed: {type(error).__name__}"
        ) from error
    result = "\n".join(str(row[0]) for row in rows)
    if result.casefold() != "ok":
        raise RequirementAcceptanceBootstrapError(
            f"SQLite integrity check did not return ok: {result[:500]}"
        )
    return result


def sqlite_revision(path: Path) -> str | None:
    try:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            ).fetchone()
            if table is None:
                return None
            row = connection.execute(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).fetchone()
            return str(row[0]) if row is not None else None
    except sqlite3.Error as error:
        raise RequirementAcceptanceBootstrapError(
            f"SQLite revision check failed: {type(error).__name__}"
        ) from error


def backup_sqlite_database(
    source_path: Path,
    backup_path: Path,
    *,
    allowed_root: Path | None = None,
) -> RequirementAcceptanceDatabaseBackupResult:
    source = source_path.resolve()
    backup = backup_path.resolve()
    if allowed_root is not None and not backup.is_relative_to(
        allowed_root.resolve()
    ):
        raise RequirementAcceptanceBootstrapError(
            "SQLite backup destination escapes the configured private root at apply time."
        )
    if not source.is_file():
        raise RequirementAcceptanceBootstrapError(
            f"SQLite source database does not exist: {source}"
        )
    if backup.exists():
        raise RequirementAcceptanceBootstrapError(
            f"Refusing to overwrite an existing SQLite backup: {backup}"
        )
    backup.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=backup.parent,
            prefix=f".{backup.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_handle:
            temp_path = Path(temp_handle.name)
        temp_path.unlink(missing_ok=True)
        try:
            with sqlite3.connect(
                f"file:{source}?mode=ro",
                uri=True,
            ) as source_connection:
                with sqlite3.connect(temp_path) as backup_connection:
                    source_connection.backup(backup_connection)
                    backup_connection.execute("PRAGMA wal_checkpoint(FULL)")
        except sqlite3.Error as error:
            raise RequirementAcceptanceBootstrapError(
                f"SQLite online backup failed: {type(error).__name__}"
            ) from error
        integrity = sqlite_integrity_check(temp_path)
        os.replace(temp_path, backup)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return RequirementAcceptanceDatabaseBackupResult(
        source_path=source,
        backup_path=backup,
        file_sha256=file_sha256(backup),
        byte_count=backup.stat().st_size,
        integrity_check=integrity,
        source_revision=sqlite_revision(backup),
    )
