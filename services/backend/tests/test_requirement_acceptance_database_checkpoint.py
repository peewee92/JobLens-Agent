"""Resumable SQLite checkpoint tests for live Requirement acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from app.application.requirement_acceptance.database_checkpoint import (
    DATABASE_CHECKPOINT_SCHEMA_VERSION,
    database_checkpoint_receipt_path,
    mark_database_checkpoint_backup_verified,
    mark_database_checkpoint_failed,
    mark_database_checkpoint_migration_attempted,
    new_database_checkpoint_receipt,
    requirement_acceptance_database_checkpoint_id,
    verify_database_checkpoint_backup,
)
from alembic import command

from app.application.requirement_acceptance.local_bootstrap import (
    RequirementAcceptanceBootstrapError,
    backup_sqlite_database,
    file_sha256,
    sqlite_integrity_check,
    sqlite_revision,
)
from app.core import config as app_config
import scripts.prepare_requirement_acceptance_database as checkpoint_cli


def _database(path: Path, revision: str = "old") -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE alembic_version (version_num TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO alembic_version(version_num) VALUES (?)",
            (revision,),
        )
        connection.execute(
            "CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO evidence(value) VALUES ('preserved')")


def _set_revision(path: Path, revision: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE alembic_version SET version_num = ?", (revision,))


def _args(
    *,
    private_root: Path,
    apply: bool,
    confirm_backend_stopped: bool,
):
    return SimpleNamespace(
        private_root=private_root,
        apply=apply,
        confirm_backend_stopped=confirm_backend_stopped,
        json=True,
    )


def _configure_cli(
    monkeypatch,
    *,
    database: Path,
    private_base: Path,
    private_root: Path,
    apply: bool,
    confirm_backend_stopped: bool,
    head: str = "head",
) -> None:
    monkeypatch.setattr(checkpoint_cli, "PRIVATE_DATA_ROOT", private_base.resolve())
    monkeypatch.setattr(
        checkpoint_cli,
        "_arguments",
        lambda: _args(
            private_root=private_root,
            apply=apply,
            confirm_backend_stopped=confirm_backend_stopped,
        ),
    )
    monkeypatch.setattr(
        checkpoint_cli,
        "get_settings",
        lambda: SimpleNamespace(database_url=f"sqlite:///{database}"),
    )
    monkeypatch.setattr(checkpoint_cli, "_migration_head", lambda: head)
    monkeypatch.setattr(
        checkpoint_cli,
        "_database_revision",
        lambda _url: (True, sqlite_revision(database), None),
    )


def test_checkpoint_identity_is_stable_for_one_database_target(tmp_path: Path) -> None:
    database = tmp_path / "joblens.db"
    first = requirement_acceptance_database_checkpoint_id(
        database_path=database,
        migration_head="head_1",
    )
    second = requirement_acceptance_database_checkpoint_id(
        database_path=database,
        migration_head="head_1",
    )
    next_head = requirement_acceptance_database_checkpoint_id(
        database_path=database,
        migration_head="head_2",
    )
    assert first == second
    assert first.startswith("reqacceptdb_")
    assert next_head != first


def test_verified_backup_evidence_detects_tampering(tmp_path: Path) -> None:
    database = tmp_path / "joblens.db"
    _database(database)
    private_root = tmp_path / "private"
    backup_result = backup_sqlite_database(
        database,
        private_root / "backups" / "joblens.db",
        allowed_root=private_root,
    )
    checkpoint_id = requirement_acceptance_database_checkpoint_id(
        database_path=database,
        migration_head="head",
    )
    receipt = new_database_checkpoint_receipt(
        checkpoint_id=checkpoint_id,
        database_path=database,
        source_revision="old",
        migration_head="head",
        backup_path=backup_result.backup_path,
    )
    receipt = mark_database_checkpoint_backup_verified(
        receipt,
        backup_path=backup_result.backup_path,
        file_sha256_value=backup_result.file_sha256,
        byte_count=backup_result.byte_count,
        integrity_check=backup_result.integrity_check,
        source_revision=backup_result.source_revision,
    )
    assert verify_database_checkpoint_backup(
        receipt,
        allowed_root=private_root,
    ) == backup_result.backup_path

    backup_result.backup_path.write_bytes(b"tampered")
    try:
        verify_database_checkpoint_backup(receipt, allowed_root=private_root)
    except RequirementAcceptanceBootstrapError as error:
        assert "SHA-256" in str(error)
    else:  # pragma: no cover
        raise AssertionError("tampered backup must not be reused")


def test_cli_plan_is_read_only_and_exposes_stable_receipt_path(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    database = tmp_path / "joblens.db"
    _database(database)
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    _configure_cli(
        monkeypatch,
        database=database,
        private_base=private_base,
        private_root=private_root,
        apply=False,
        confirm_backend_stopped=False,
    )

    assert checkpoint_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["state"] == "planned"
    assert body["applyExecuted"] is False
    assert body["migrationNeeded"] is True
    assert body["providerCalls"] == 0
    assert body["acceptanceDomainWrites"] == 0
    assert private_root.exists() is False
    assert sqlite_revision(database) == "old"


def test_cli_requires_backend_stopped_confirmation_before_mutation(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    database = tmp_path / "joblens.db"
    _database(database)
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    _configure_cli(
        monkeypatch,
        database=database,
        private_base=private_base,
        private_root=private_root,
        apply=True,
        confirm_backend_stopped=False,
    )

    assert checkpoint_cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert body["blockers"] == [
        "Pending SQLite migration requires --confirm-backend-stopped."
    ]
    assert private_root.exists() is False
    assert sqlite_revision(database) == "old"


def test_cli_apply_creates_verified_backup_migrates_and_persists_checkpoint(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    database = tmp_path / "joblens.db"
    _database(database)
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    _configure_cli(
        monkeypatch,
        database=database,
        private_base=private_base,
        private_root=private_root,
        apply=True,
        confirm_backend_stopped=True,
    )
    calls = []

    def upgrade() -> None:
        calls.append("upgrade")
        _set_revision(database, "head")

    monkeypatch.setattr(checkpoint_cli, "_upgrade_database_to_head", upgrade)

    assert checkpoint_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    receipt = json.loads(Path(body["receiptPath"]).read_text(encoding="utf-8"))
    assert calls == ["upgrade"]
    assert body["state"] == "applied"
    assert body["backupVerified"] is True
    assert body["migrationAttempted"] is True
    assert body["migrationApplied"] is True
    assert body["integrityAfter"] == "ok"
    assert receipt["schemaVersion"] == DATABASE_CHECKPOINT_SCHEMA_VERSION
    assert receipt["state"] == "applied"
    assert sqlite_revision(database) == "head"
    assert sqlite_integrity_check(database) == "ok"
    backup = Path(body["backupPath"])
    assert backup.is_file()
    assert file_sha256(backup) == receipt["backup"]["fileSha256"]
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT value FROM evidence").fetchone() == (
            "preserved",
        )


def test_cli_reuses_verified_backup_after_interrupted_checkpoint(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    database = tmp_path / "joblens.db"
    _database(database)
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    checkpoint_id = requirement_acceptance_database_checkpoint_id(
        database_path=database,
        migration_head="head",
    )
    receipt_path = database_checkpoint_receipt_path(
        private_root=private_root,
        checkpoint_id=checkpoint_id,
    )
    backup_result = backup_sqlite_database(
        database,
        private_root / "backups" / "existing.db",
        allowed_root=private_root,
    )
    receipt = new_database_checkpoint_receipt(
        checkpoint_id=checkpoint_id,
        database_path=database,
        source_revision="old",
        migration_head="head",
        backup_path=backup_result.backup_path,
    )
    receipt = mark_database_checkpoint_backup_verified(
        receipt,
        backup_path=backup_result.backup_path,
        file_sha256_value=backup_result.file_sha256,
        byte_count=backup_result.byte_count,
        integrity_check=backup_result.integrity_check,
        source_revision=backup_result.source_revision,
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _configure_cli(
        monkeypatch,
        database=database,
        private_base=private_base,
        private_root=private_root,
        apply=True,
        confirm_backend_stopped=True,
    )
    monkeypatch.setattr(
        checkpoint_cli,
        "_upgrade_database_to_head",
        lambda: _set_revision(database, "head"),
    )

    assert checkpoint_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["backupReused"] is True
    assert list((private_root / "backups").glob("*")) == [
        backup_result.backup_path
    ]


def test_cli_recovers_when_database_reached_head_before_final_receipt(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    database = tmp_path / "joblens.db"
    _database(database)
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    checkpoint_id = requirement_acceptance_database_checkpoint_id(
        database_path=database,
        migration_head="head",
    )
    receipt_path = database_checkpoint_receipt_path(
        private_root=private_root,
        checkpoint_id=checkpoint_id,
    )
    backup_result = backup_sqlite_database(
        database,
        private_root / "backups" / "existing.db",
        allowed_root=private_root,
    )
    receipt = new_database_checkpoint_receipt(
        checkpoint_id=checkpoint_id,
        database_path=database,
        source_revision="old",
        migration_head="head",
        backup_path=backup_result.backup_path,
    )
    receipt = mark_database_checkpoint_backup_verified(
        receipt,
        backup_path=backup_result.backup_path,
        file_sha256_value=backup_result.file_sha256,
        byte_count=backup_result.byte_count,
        integrity_check=backup_result.integrity_check,
        source_revision=backup_result.source_revision,
    )
    receipt = mark_database_checkpoint_migration_attempted(receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _set_revision(database, "head")
    _configure_cli(
        monkeypatch,
        database=database,
        private_base=private_base,
        private_root=private_root,
        apply=True,
        confirm_backend_stopped=False,
    )
    monkeypatch.setattr(
        checkpoint_cli,
        "_upgrade_database_to_head",
        lambda: (_ for _ in ()).throw(AssertionError("must not migrate twice")),
    )

    assert checkpoint_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["state"] == "applied"
    assert body["recoveredAfterCrash"] is True
    assert body["backupReused"] is True


def test_cli_records_failed_migration_and_next_run_refuses_retry(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    database = tmp_path / "joblens.db"
    _database(database)
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    _configure_cli(
        monkeypatch,
        database=database,
        private_base=private_base,
        private_root=private_root,
        apply=True,
        confirm_backend_stopped=True,
    )

    def fail_upgrade() -> None:
        raise RequirementAcceptanceBootstrapError("simulated migration failure")

    monkeypatch.setattr(checkpoint_cli, "_upgrade_database_to_head", fail_upgrade)

    assert checkpoint_cli.main() == 2
    first = json.loads(capsys.readouterr().out)
    receipt_path = Path(first["receiptPath"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert first["state"] == "failed"
    assert first["backupVerified"] is True
    assert first["migrationAttempted"] is True
    assert receipt["failure"]["message"] == "simulated migration failure"
    assert sqlite_revision(database) == "old"

    monkeypatch.setattr(
        checkpoint_cli,
        "_upgrade_database_to_head",
        lambda: (_ for _ in ()).throw(AssertionError("must not retry")),
    )
    assert checkpoint_cli.main() == 2
    second = json.loads(capsys.readouterr().out)
    assert "inconclusive" in second["blockers"][0]
    assert second["backupVerified"] is True
    assert sqlite_revision(database) == "old"


def test_cli_reuses_backup_after_failure_before_migration_attempt(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    database = tmp_path / "joblens.db"
    _database(database)
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    checkpoint_id = requirement_acceptance_database_checkpoint_id(
        database_path=database,
        migration_head="head",
    )
    receipt_path = database_checkpoint_receipt_path(
        private_root=private_root,
        checkpoint_id=checkpoint_id,
    )
    backup_result = backup_sqlite_database(
        database,
        private_root / "backups" / "existing.db",
        allowed_root=private_root,
    )
    receipt = new_database_checkpoint_receipt(
        checkpoint_id=checkpoint_id,
        database_path=database,
        source_revision="old",
        migration_head="head",
        backup_path=backup_result.backup_path,
    )
    receipt = mark_database_checkpoint_backup_verified(
        receipt,
        backup_path=backup_result.backup_path,
        file_sha256_value=backup_result.file_sha256,
        byte_count=backup_result.byte_count,
        integrity_check=backup_result.integrity_check,
        source_revision=backup_result.source_revision,
    )
    receipt = mark_database_checkpoint_failed(
        receipt,
        error=RequirementAcceptanceBootstrapError("receipt write interruption"),
        revision_after="old",
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _configure_cli(
        monkeypatch,
        database=database,
        private_base=private_base,
        private_root=private_root,
        apply=True,
        confirm_backend_stopped=True,
    )
    monkeypatch.setattr(
        checkpoint_cli,
        "_upgrade_database_to_head",
        lambda: _set_revision(database, "head"),
    )

    assert checkpoint_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["state"] == "applied"
    assert body["backupReused"] is True
    assert sqlite_revision(database) == "head"


def test_cli_refuses_to_retry_an_inconclusive_previous_migration(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    database = tmp_path / "joblens.db"
    _database(database)
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    checkpoint_id = requirement_acceptance_database_checkpoint_id(
        database_path=database,
        migration_head="head",
    )
    receipt_path = database_checkpoint_receipt_path(
        private_root=private_root,
        checkpoint_id=checkpoint_id,
    )
    backup_result = backup_sqlite_database(
        database,
        private_root / "backups" / "existing.db",
        allowed_root=private_root,
    )
    receipt = new_database_checkpoint_receipt(
        checkpoint_id=checkpoint_id,
        database_path=database,
        source_revision="old",
        migration_head="head",
        backup_path=backup_result.backup_path,
    )
    receipt = mark_database_checkpoint_backup_verified(
        receipt,
        backup_path=backup_result.backup_path,
        file_sha256_value=backup_result.file_sha256,
        byte_count=backup_result.byte_count,
        integrity_check=backup_result.integrity_check,
        source_revision=backup_result.source_revision,
    )
    receipt = mark_database_checkpoint_migration_attempted(receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _configure_cli(
        monkeypatch,
        database=database,
        private_base=private_base,
        private_root=private_root,
        apply=True,
        confirm_backend_stopped=True,
    )
    monkeypatch.setattr(
        checkpoint_cli,
        "_upgrade_database_to_head",
        lambda: (_ for _ in ()).throw(AssertionError("must not retry")),
    )

    assert checkpoint_cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert "inconclusive" in body["blockers"][0]
    assert body["migrationAttempted"] is True
    assert sqlite_revision(database) == "old"


def test_cli_blocks_unexpected_intermediate_revision(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    database = tmp_path / "joblens.db"
    _database(database, revision="middle")
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    checkpoint_id = requirement_acceptance_database_checkpoint_id(
        database_path=database,
        migration_head="head",
    )
    receipt_path = database_checkpoint_receipt_path(
        private_root=private_root,
        checkpoint_id=checkpoint_id,
    )
    receipt = new_database_checkpoint_receipt(
        checkpoint_id=checkpoint_id,
        database_path=database,
        source_revision="old",
        migration_head="head",
        backup_path=private_root / "backups" / "old.db",
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _configure_cli(
        monkeypatch,
        database=database,
        private_base=private_base,
        private_root=private_root,
        apply=True,
        confirm_backend_stopped=True,
    )

    assert checkpoint_cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert "no longer matches" in body["blockers"][0]
    assert sqlite_revision(database) == "middle"


def test_real_database_checkpoint_upgrade_helper_reaches_head(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "migration.db"
    database_url = f"sqlite:///{database}"
    monkeypatch.setattr(app_config.settings, "database_url", database_url)
    config = checkpoint_cli._alembic_config()
    command.upgrade(config, "20260803_0010")
    assert sqlite_revision(database) == "20260803_0010"

    checkpoint_cli._upgrade_database_to_head()

    assert sqlite_revision(database) == checkpoint_cli._migration_head()
    assert sqlite_integrity_check(database) == "ok"


def test_cli_rejects_unknown_checkpoint_state(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    database = tmp_path / "joblens.db"
    _database(database)
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    checkpoint_id = requirement_acceptance_database_checkpoint_id(
        database_path=database,
        migration_head="head",
    )
    receipt_path = database_checkpoint_receipt_path(
        private_root=private_root,
        checkpoint_id=checkpoint_id,
    )
    receipt = new_database_checkpoint_receipt(
        checkpoint_id=checkpoint_id,
        database_path=database,
        source_revision="old",
        migration_head="head",
        backup_path=private_root / "backups" / "old.db",
    )
    receipt["state"] = "mystery"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _configure_cli(
        monkeypatch,
        database=database,
        private_base=private_base,
        private_root=private_root,
        apply=False,
        confirm_backend_stopped=False,
    )

    assert checkpoint_cli.main() == 2
    assert "state is invalid" in capsys.readouterr().out


def test_checkpoint_source_contains_no_provider_or_acceptance_execution() -> None:
    source = Path(checkpoint_cli.__file__).read_text(encoding="utf-8")
    forbidden = (
        "build_job_requirement_extractor",
        "PrepareRequirementAcceptanceBatchUseCase",
        "ImportJobsUseCase",
        "openai_api_key",
        "httpx",
        "requests",
        "except Exception",
    )
    for token in forbidden:
        assert token not in source
