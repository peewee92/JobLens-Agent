"""Guarded local bootstrap tests for live Requirement acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from alembic import command

from app.application.requirement_acceptance.local_bootstrap import (
    RequirementAcceptanceBootstrapError,
    backup_sqlite_database,
    build_requirement_acceptance_bootstrap_plan,
    file_sha256,
    sqlite_integrity_check,
    sqlite_revision,
    stage_private_dataset,
)
from app.application.requirement_acceptance.runs import RequirementAcceptancePreflight
from app.core import config as app_config
import scripts.bootstrap_requirement_acceptance as bootstrap_cli


def _preflight() -> RequirementAcceptancePreflight:
    return RequirementAcceptancePreflight(
        dataset_fingerprint="a" * 64,
        source_version="1.4.6",
        generated_at="2026-08-04T12:00:00Z",
        selected_count=20,
        total_description_characters=20_000,
        minimum_description_characters=500,
        maximum_description_characters=1_500,
        average_description_characters=1_000.0,
    )


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
        connection.execute(
            "INSERT INTO evidence(value) VALUES ('preserved')"
        )


def _args(
    *,
    dataset: Path,
    private_root: Path,
    apply: bool,
    confirm_backend_stopped: bool,
    receipt: Path | None = None,
):
    return SimpleNamespace(
        dataset=dataset,
        reviewer="will",
        title="Real Requirement acceptance",
        max_new_extractions=3,
        web_base_url="http://localhost:3000",
        private_root=private_root,
        apply=apply,
        confirm_backend_stopped=confirm_backend_stopped,
        receipt=receipt,
        json=True,
    )


def test_plan_is_deterministic_and_does_not_write(tmp_path: Path) -> None:
    dataset = tmp_path / "formal.json"
    dataset.write_bytes(b'{"formal":true}')
    database = tmp_path / "joblens.db"
    _database(database, revision="revision_old")
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"

    plan = build_requirement_acceptance_bootstrap_plan(
        dataset_source_path=dataset,
        dataset_fingerprint="a" * 64,
        private_root=private_root,
        database_url=f"sqlite:///{database}",
        backend_root=tmp_path,
        database_revision="revision_old",
        migration_head="revision_head",
        database_reachable=True,
    )

    assert plan.apply_allowed is True
    assert plan.dataset_stage_needed is True
    assert plan.dataset_destination_path == (
        private_root / "datasets" / f"formal-{'a' * 16}.json"
    )
    assert plan.migration_needed is True
    assert plan.planned_backup_path is not None
    assert private_root.exists() is False
    assert sqlite_revision(database) == "revision_old"


def test_dataset_staging_is_verified_idempotent_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    source = tmp_path / "formal.json"
    source.write_bytes(b"formal-dataset")
    destination = tmp_path / "private" / "formal.json"

    first = stage_private_dataset(source, destination)
    second = stage_private_dataset(source, destination)
    assert first.reused is False
    assert second.reused is True
    assert first.file_sha256 == file_sha256(source) == file_sha256(destination)
    assert list(destination.parent.glob(f".{destination.name}.*.tmp")) == []

    destination.write_bytes(b"different")
    try:
        stage_private_dataset(source, destination)
    except RequirementAcceptanceBootstrapError as error:
        assert "different bytes" in str(error)
    else:  # pragma: no cover - explicit failure assertion
        raise AssertionError("staging must refuse a mismatched existing file")


def test_sqlite_online_backup_is_consistent_and_preserves_revision(
    tmp_path: Path,
) -> None:
    database = tmp_path / "joblens.db"
    _database(database, revision="revision_old")
    backup = tmp_path / "private" / "backup.db"

    result = backup_sqlite_database(database, backup)

    assert result.integrity_check == "ok"
    assert result.source_revision == "revision_old"
    assert result.file_sha256 == file_sha256(backup)
    assert sqlite_integrity_check(backup) == "ok"
    with sqlite3.connect(backup) as connection:
        row = connection.execute("SELECT value FROM evidence").fetchone()
        assert row == ("preserved",)


def test_plan_rejects_non_sqlite_and_mismatched_private_dataset(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "formal.json"
    dataset.write_bytes(b"source")
    private_root = tmp_path / "private"
    destination = private_root / "datasets" / f"formal-{'a' * 16}.json"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"other")

    plan = build_requirement_acceptance_bootstrap_plan(
        dataset_source_path=dataset,
        dataset_fingerprint="a" * 64,
        private_root=private_root,
        database_url="postgresql://localhost/joblens",
        backend_root=tmp_path,
        database_revision="old",
        migration_head="head",
        database_reachable=True,
    )
    assert plan.apply_allowed is False
    assert any("SQLite only" in blocker for blocker in plan.blockers)
    assert any("different bytes" in blocker for blocker in plan.blockers)


def test_plan_rejects_symlink_escape_from_private_root(tmp_path: Path) -> None:
    dataset = tmp_path / "formal.json"
    dataset.write_bytes(b"source")
    database = tmp_path / "joblens.db"
    _database(database, revision="old")
    private_root = tmp_path / "project" / "data" / "private" / "requirement-acceptance"
    private_root.mkdir(parents=True)
    outside_datasets = tmp_path / "tracked" / "datasets"
    outside_backups = tmp_path / "tracked" / "backups"
    outside_datasets.mkdir(parents=True)
    outside_backups.mkdir(parents=True)
    (private_root / "datasets").symlink_to(outside_datasets, target_is_directory=True)
    (private_root / "backups").symlink_to(outside_backups, target_is_directory=True)

    plan = build_requirement_acceptance_bootstrap_plan(
        dataset_source_path=dataset,
        dataset_fingerprint="a" * 64,
        private_root=private_root,
        database_url=f"sqlite:///{database}",
        backend_root=tmp_path,
        database_revision="old",
        migration_head="head",
        database_reachable=True,
    )

    assert plan.apply_allowed is False
    assert any("dataset destination escapes" in item for item in plan.blockers)
    assert any("backup destination escapes" in item for item in plan.blockers)


def test_apply_time_private_root_check_rejects_late_symlink_escape(
    tmp_path: Path,
) -> None:
    source = tmp_path / "formal.json"
    source.write_bytes(b"formal")
    private_root = tmp_path / "private"
    outside = tmp_path / "tracked"
    private_root.mkdir()
    outside.mkdir()
    datasets = private_root / "datasets"
    datasets.symlink_to(outside, target_is_directory=True)

    try:
        stage_private_dataset(
            source,
            datasets / "formal.json",
            allowed_root=private_root,
        )
    except RequirementAcceptanceBootstrapError as error:
        assert "apply time" in str(error)
    else:  # pragma: no cover - explicit failure assertion
        raise AssertionError("apply-time staging must reject symlink escape")


def test_cli_plan_mode_has_zero_mutations(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "formal.json"
    dataset.write_bytes(b'{"formal":true}')
    database = tmp_path / "joblens.db"
    _database(database, revision="old")
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"

    monkeypatch.setattr(bootstrap_cli, "PRIVATE_DATA_ROOT", private_base.resolve())
    monkeypatch.setattr(
        bootstrap_cli,
        "_arguments",
        lambda: _args(
            dataset=dataset,
            private_root=private_root,
            apply=False,
            confirm_backend_stopped=False,
        ),
    )
    monkeypatch.setattr(bootstrap_cli, "_load_payload", lambda _path: {"formal": True})
    monkeypatch.setattr(
        bootstrap_cli,
        "preflight_requirement_acceptance_dataset",
        lambda _payload: _preflight(),
    )
    monkeypatch.setattr(bootstrap_cli, "_migration_head", lambda: "head")
    monkeypatch.setattr(
        bootstrap_cli,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=f"sqlite:///{database}",
            requirement_extractor_provider="disabled",
            requirement_extractor_model="",
            openai_api_key=None,
        ),
    )

    assert bootstrap_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["mode"] == "plan"
    assert body["planValidated"] is True
    assert body["applyExecuted"] is False
    assert body["localPreparationSucceeded"] is False
    assert body["providerCalls"] == 0
    assert body["acceptanceDomainWrites"] == 0
    assert body["mutations"] == {
        "datasetStaged": False,
        "databaseBackupCreated": False,
        "migrationAttempted": False,
        "migrationApplied": False,
    }
    assert private_root.exists() is False
    assert sqlite_revision(database) == "old"


def test_cli_apply_stages_backs_up_upgrades_and_rechecks_readiness(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "formal.json"
    dataset.write_bytes(b'{"formal":true}')
    database = tmp_path / "joblens.db"
    _database(database, revision="old")
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    receipt = private_root / "receipts" / "bootstrap.json"

    monkeypatch.setattr(bootstrap_cli, "PRIVATE_DATA_ROOT", private_base.resolve())
    monkeypatch.setattr(
        bootstrap_cli,
        "_arguments",
        lambda: _args(
            dataset=dataset,
            private_root=private_root,
            apply=True,
            confirm_backend_stopped=True,
            receipt=receipt,
        ),
    )
    monkeypatch.setattr(bootstrap_cli, "_load_payload", lambda _path: {"formal": True})
    monkeypatch.setattr(
        bootstrap_cli,
        "preflight_requirement_acceptance_dataset",
        lambda _payload: _preflight(),
    )
    monkeypatch.setattr(bootstrap_cli, "_migration_head", lambda: "head")
    monkeypatch.setattr(
        bootstrap_cli,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=f"sqlite:///{database}",
            requirement_extractor_provider="disabled",
            requirement_extractor_model="",
            openai_api_key=None,
        ),
    )

    def upgrade() -> None:
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE alembic_version SET version_num='head'")

    monkeypatch.setattr(bootstrap_cli, "_upgrade_database_to_head", upgrade)

    assert bootstrap_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["localPreparationSucceeded"] is True
    assert body["mutations"] == {
        "datasetStaged": True,
        "databaseBackupCreated": True,
        "migrationAttempted": True,
        "migrationApplied": True,
    }
    assert body["databaseRevisionAfter"] == "head"
    assert body["databaseIntegrityAfter"] == "ok"
    assert body["readiness"]["nextAction"] == "fix_blockers"
    assert body["readiness"]["providerExecutionAllowed"] is False
    staged = Path(body["datasetStage"]["destinationPath"])
    backup = Path(body["databaseBackup"]["path"])
    assert staged.read_bytes() == dataset.read_bytes()
    assert sqlite_revision(backup) == "old"
    assert sqlite_revision(database) == "head"
    receipt_body = json.loads(receipt.read_text(encoding="utf-8"))
    assert receipt_body["localPreparationSucceeded"] is True
    assert receipt_body["outputWrites"]["receiptWritten"] is True
    assert "OPENAI_API_KEY" not in json.dumps(body)


def test_readiness_preview_receives_next_action_and_existing_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "formal.json"
    dataset.write_bytes(b'{"formal":true}')
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        bootstrap_cli,
        "_database_revision",
        lambda _database_url: (True, "head", None),
    )
    monkeypatch.setattr(bootstrap_cli, "_existing_run", lambda **_kwargs: None)

    def command_preview(**kwargs) -> str:
        captured.update(kwargs)
        return "preview"

    monkeypatch.setattr(bootstrap_cli, "_command_preview", command_preview)

    summary = bootstrap_cli._readiness_after_bootstrap(
        dataset_path=dataset,
        preflight=_preflight(),
        reviewer="will",
        title="Real Requirement acceptance",
        max_new_extractions=1,
        web_base_url="http://localhost:3000",
        settings=SimpleNamespace(
            database_url="sqlite:///ignored.db",
            requirement_extractor_provider="openai",
            requirement_extractor_model="deepseek-v4-flash",
            openai_api_key="configured",
        ),
        migration_head="head",
    )

    assert summary["nextAction"] == "run_canary"
    assert summary["providerExecutionAllowed"] is True
    assert summary["recommendedCommand"] == "preview"
    assert captured["dataset"] == dataset
    assert captured["existing_run"] is None
    assert captured["next_action"].value == "run_canary"


def test_backup_failure_prevents_migration(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "formal.json"
    dataset.write_bytes(b'{"formal":true}')
    database = tmp_path / "joblens.db"
    _database(database, revision="old")
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    upgraded = False

    monkeypatch.setattr(bootstrap_cli, "PRIVATE_DATA_ROOT", private_base.resolve())
    monkeypatch.setattr(
        bootstrap_cli,
        "_arguments",
        lambda: _args(
            dataset=dataset,
            private_root=private_root,
            apply=True,
            confirm_backend_stopped=True,
        ),
    )
    monkeypatch.setattr(bootstrap_cli, "_load_payload", lambda _path: {"formal": True})
    monkeypatch.setattr(
        bootstrap_cli,
        "preflight_requirement_acceptance_dataset",
        lambda _payload: _preflight(),
    )
    monkeypatch.setattr(bootstrap_cli, "_migration_head", lambda: "head")
    monkeypatch.setattr(
        bootstrap_cli,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=f"sqlite:///{database}",
            requirement_extractor_provider="disabled",
            requirement_extractor_model="",
            openai_api_key=None,
        ),
    )
    monkeypatch.setattr(
        bootstrap_cli,
        "backup_sqlite_database",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RequirementAcceptanceBootstrapError("backup failed")
        ),
    )

    def upgrade() -> None:
        nonlocal upgraded
        upgraded = True

    monkeypatch.setattr(bootstrap_cli, "_upgrade_database_to_head", upgrade)

    assert bootstrap_cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert upgraded is False
    assert body["mutations"]["databaseBackupCreated"] is False
    assert body["mutations"]["migrationAttempted"] is False
    assert body["mutations"]["migrationApplied"] is False
    assert body["failure"]["verifiedBackupPath"] is None
    assert sqlite_revision(database) == "old"


def test_migration_failure_preserves_verified_backup_and_records_attempt(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "formal.json"
    dataset.write_bytes(b'{"formal":true}')
    database = tmp_path / "joblens.db"
    _database(database, revision="old")
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"

    monkeypatch.setattr(bootstrap_cli, "PRIVATE_DATA_ROOT", private_base.resolve())
    monkeypatch.setattr(
        bootstrap_cli,
        "_arguments",
        lambda: _args(
            dataset=dataset,
            private_root=private_root,
            apply=True,
            confirm_backend_stopped=True,
        ),
    )
    monkeypatch.setattr(bootstrap_cli, "_load_payload", lambda _path: {"formal": True})
    monkeypatch.setattr(
        bootstrap_cli,
        "preflight_requirement_acceptance_dataset",
        lambda _payload: _preflight(),
    )
    monkeypatch.setattr(bootstrap_cli, "_migration_head", lambda: "head")
    monkeypatch.setattr(
        bootstrap_cli,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=f"sqlite:///{database}",
            requirement_extractor_provider="disabled",
            requirement_extractor_model="",
            openai_api_key=None,
        ),
    )

    def partial_upgrade() -> None:
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE alembic_version SET version_num='partial'")
        raise RequirementAcceptanceBootstrapError("migration failed after partial DDL")

    monkeypatch.setattr(bootstrap_cli, "_upgrade_database_to_head", partial_upgrade)

    assert bootstrap_cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert body["mutations"]["databaseBackupCreated"] is True
    assert body["mutations"]["migrationAttempted"] is True
    assert body["mutations"]["migrationApplied"] is False
    backup = Path(body["failure"]["verifiedBackupPath"])
    assert sqlite_revision(backup) == "old"
    assert sqlite_revision(database) == "partial"
    assert "migration failed" in body["failure"]["message"]


def test_apply_requires_backend_stopped_only_when_migration_is_pending(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "formal.json"
    dataset.write_bytes(b'{"formal":true}')
    database = tmp_path / "joblens.db"
    _database(database, revision="old")
    private_base = tmp_path / "project" / "data" / "private"

    monkeypatch.setattr(bootstrap_cli, "PRIVATE_DATA_ROOT", private_base.resolve())
    monkeypatch.setattr(
        bootstrap_cli,
        "_arguments",
        lambda: _args(
            dataset=dataset,
            private_root=private_base / "requirement-acceptance",
            apply=True,
            confirm_backend_stopped=False,
        ),
    )
    monkeypatch.setattr(bootstrap_cli, "_load_payload", lambda _path: {"formal": True})
    monkeypatch.setattr(
        bootstrap_cli,
        "preflight_requirement_acceptance_dataset",
        lambda _payload: _preflight(),
    )
    monkeypatch.setattr(bootstrap_cli, "_migration_head", lambda: "head")
    monkeypatch.setattr(
        bootstrap_cli,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=f"sqlite:///{database}",
            requirement_extractor_provider="disabled",
            requirement_extractor_model="",
            openai_api_key=None,
        ),
    )

    assert bootstrap_cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert any("confirm-backend-stopped" in item for item in body["plan"]["blockers"])
    assert (private_base / "requirement-acceptance").exists() is False


def test_receipt_must_stay_under_selected_private_root(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "formal.json"
    dataset.write_bytes(b'{"formal":true}')
    database = tmp_path / "joblens.db"
    _database(database, revision="head")
    private_base = tmp_path / "project" / "data" / "private"
    private_root = private_base / "requirement-acceptance"
    monkeypatch.setattr(bootstrap_cli, "PRIVATE_DATA_ROOT", private_base.resolve())
    monkeypatch.setattr(
        bootstrap_cli,
        "_arguments",
        lambda: _args(
            dataset=dataset,
            private_root=private_root,
            apply=False,
            confirm_backend_stopped=False,
            receipt=tmp_path / "project" / "docs" / "receipt.json",
        ),
    )
    monkeypatch.setattr(bootstrap_cli, "_load_payload", lambda _path: {"formal": True})
    monkeypatch.setattr(
        bootstrap_cli,
        "preflight_requirement_acceptance_dataset",
        lambda _payload: _preflight(),
    )

    assert bootstrap_cli.main() == 2
    assert "--receipt" in capsys.readouterr().out


def test_private_root_must_stay_under_git_ignored_data_private(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "formal.json"
    dataset.write_bytes(b'{"formal":true}')
    private_base = tmp_path / "project" / "data" / "private"
    monkeypatch.setattr(bootstrap_cli, "PRIVATE_DATA_ROOT", private_base.resolve())
    monkeypatch.setattr(
        bootstrap_cli,
        "_arguments",
        lambda: _args(
            dataset=dataset,
            private_root=tmp_path / "project" / "docs",
            apply=False,
            confirm_backend_stopped=False,
        ),
    )
    monkeypatch.setattr(bootstrap_cli, "_load_payload", lambda _path: {"formal": True})
    monkeypatch.setattr(
        bootstrap_cli,
        "preflight_requirement_acceptance_dataset",
        lambda _payload: _preflight(),
    )

    assert bootstrap_cli.main() == 2
    assert "data/private" in capsys.readouterr().out


def test_real_alembic_upgrade_helper_reaches_head(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "migration.db"
    database_url = f"sqlite:///{database}"
    monkeypatch.setattr(app_config.settings, "database_url", database_url)
    config = bootstrap_cli._alembic_config()
    command.upgrade(config, "20260803_0010")
    assert sqlite_revision(database) == "20260803_0010"

    bootstrap_cli._upgrade_database_to_head()

    assert sqlite_revision(database) == bootstrap_cli._migration_head()
    assert sqlite_integrity_check(database) == "ok"


def test_bootstrap_source_has_no_provider_or_domain_execution() -> None:
    source = Path(bootstrap_cli.__file__).read_text(encoding="utf-8")
    assert "build_job_requirement_extractor" not in source
    assert "ImportJobsUseCase" not in source
    assert "PrepareRequirementAcceptanceBatchUseCase" not in source
    assert "OPENAI_API_KEY" not in source
    assert "except Exception" not in source
