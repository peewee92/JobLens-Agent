from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, text

from app.api.v1.health import get_readiness_probe
from app.api.v1.schemas.system_readiness import SystemReadinessResponse
from app.repositories.sqlalchemy_system_readiness import SystemReadinessProbe
from app.main import create_app
from scripts.verify_migration_copy import verify_copy

ROOT = Path(__file__).resolve().parents[1]


def migrate(path: Path, revision: str = "head") -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path}", "OPENAI_API_KEY": ""}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision], cwd=ROOT,
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(scope="module")
def migrated_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("readiness") / "latest.db"
    migrate(path)
    return path


def test_latest_database_is_ready_without_write_statements(migrated_path):
    engine = create_engine(f"sqlite:///{migrated_path}")
    statements = []
    event.listen(engine, "before_cursor_execute", lambda c, cur, statement, *args: statements.append(statement))
    try:
        result = SystemReadinessProbe(engine).execute()
        assert result.ready and result.code == "ready"
        assert result.current_revisions == result.required_revisions
        assert result.missing_tables == ()
        assert statements
        assert not any(s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE")) for s in statements)
    finally:
        engine.dispose()


def test_missing_sqlite_database_is_not_created(tmp_path):
    path = tmp_path / "missing.db"
    engine = create_engine(f"sqlite:///{path}")
    try:
        result = SystemReadinessProbe(engine).execute()
        assert result.code == "database_unavailable"
        assert not result.ready and not path.exists()
    finally:
        engine.dispose()


def test_literal_percent_in_database_path_is_not_uri_decoded(tmp_path):
    path = tmp_path / "local%20data.db"
    path.touch()
    engine = create_engine(f"sqlite:///{path}")
    try:
        assert SystemReadinessProbe(engine).execute().code == "migration_required"
    finally:
        engine.dispose()


def test_empty_database_requires_migration_without_creating_tables(tmp_path):
    path = tmp_path / "empty.db"
    path.touch()
    engine = create_engine(f"sqlite:///{path}")
    try:
        result = SystemReadinessProbe(engine).execute()
        assert result.code == "migration_required"
        assert result.current_revisions == ()
        assert "application_workspaces" in result.missing_tables
        assert path.stat().st_size == 0
    finally:
        engine.dispose()


def test_old_database_reports_required_revision(tmp_path):
    path = tmp_path / "old.db"
    migrate(path, "20260810_0017")
    engine = create_engine(f"sqlite:///{path}")
    try:
        result = SystemReadinessProbe(engine).execute()
        assert result.code == "migration_required"
        assert result.current_revisions == ("20260810_0017",)
        assert result.tables == "failed"
        assert "application_workspaces" in result.missing_tables
    finally:
        engine.dispose()


def test_head_stamp_does_not_hide_missing_table(tmp_path):
    path = tmp_path / "damaged.db"
    migrate(path)
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE application_workspaces"))
        result = SystemReadinessProbe(engine).execute()
        assert result.code == "schema_incomplete"
        assert result.migrations == "passed"
        assert result.missing_tables == ("application_workspaces",)
    finally:
        engine.dispose()


def test_invalid_database_does_not_leak_connection_details(tmp_path):
    path = tmp_path / "private-name.db"
    path.write_bytes(b"not a sqlite database")
    engine = create_engine(f"sqlite:///{path}")
    try:
        result = SystemReadinessProbe(engine).execute()
        assert result.code == "database_unavailable"
        body = SystemReadinessResponse.from_result(result).model_dump_json()
        assert str(path) not in body and "SQLAlchemy" not in body
    finally:
        engine.dispose()


def test_missing_migration_files_fail_closed(migrated_path, tmp_path):
    engine = create_engine(f"sqlite:///{migrated_path}")
    try:
        result = SystemReadinessProbe(engine, tmp_path / "absent").execute()
        assert result.code == "migration_metadata_unavailable"
        assert not result.ready
    finally:
        engine.dispose()


@pytest.mark.parametrize("ready", [True, False])
def test_api_status_contract_and_liveness_are_separate(migrated_path, tmp_path, ready):
    path = migrated_path if ready else tmp_path / "missing.db"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    app = create_app()
    app.dependency_overrides[get_readiness_probe] = lambda: SystemReadinessProbe(engine)
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/health").status_code == 200
            response = client.get("/api/v1/readiness")
        assert response.status_code == (200 if ready else 503)
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert body["ready"] is ready
        contract = json.loads((ROOT.parents[1] / "packages/contracts/schemas/system-readiness.schema.json").read_text())
        assert set(body) == set(contract["required"])
        assert body["code"] in contract["properties"]["code"]["enum"]
        assert set(body["checks"]) == set(contract["properties"]["checks"]["required"])
        SystemReadinessResponse.model_validate(body)
    finally:
        engine.dispose()


def test_migration_copy_preserves_source_and_existing_rows(tmp_path):
    source, output = tmp_path / "source.db", tmp_path / "copy.db"
    migrate(source, "20260810_0017")
    engine = create_engine(f"sqlite:///{source}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE preservation_sentinel (id INTEGER PRIMARY KEY, note TEXT)"))
            connection.execute(text("INSERT INTO preservation_sentinel VALUES (1, 'keep this original row')"))
    finally:
        engine.dispose()
    before = source.read_bytes()
    result = verify_copy(source, output)
    assert result["existingRowsPreserved"] is True and result["ready"] is True
    assert source.read_bytes() == before
    assert output.stat().st_mode & 0o777 == 0o600
    engine = create_engine(f"sqlite:///{output}")
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT note FROM preservation_sentinel")).scalar() == "keep this original row"
    finally:
        engine.dispose()


def test_migration_copy_refuses_to_overwrite(tmp_path):
    source, output = tmp_path / "source.db", tmp_path / "existing.db"
    source.write_bytes(b"source")
    output.write_bytes(b"do not touch")
    with pytest.raises(ValueError, match="new file"):
        verify_copy(source, output)
    with pytest.raises(ValueError, match="new file"):
        verify_copy(source, source)
    assert output.read_bytes() == b"do not touch" and source.read_bytes() == b"source"
