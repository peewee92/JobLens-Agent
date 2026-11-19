from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy.exc import OperationalError

from scripts.migrate_private_workspace import (
    BUSINESS_TABLES, MigrationRefused, fingerprint, open_snapshot, ordered_tables, private_target,
)


def test_copy_scope_preserves_foreign_keys_and_excludes_model_authorizations():
    positions = {t.name: i for i, t in enumerate(ordered_tables())}
    assert positions.keys() == BUSINESS_TABLES
    assert "requirement_calls" not in positions
    assert "semantic_calls" not in positions
    for table in ordered_tables():
        assert all(positions[fk.column.table.name] < positions[table.name] for fk in table.foreign_keys)


def test_cloud_target_must_use_verified_tls_and_explicit_private_database():
    with pytest.raises(MigrationRefused, match="verify-full"):
        private_target("postgresql://user:secret@db.example.com/joblens_private?sslmode=require")
    with pytest.raises(MigrationRefused, match="系统库"):
        private_target("postgresql://user:secret@db.example.com/postgres?sslmode=verify-full")
    with pytest.raises(MigrationRefused, match="未支持"):
        private_target("postgresql://user:secret@db.example.com/joblens_private?sslmode=verify-full&host=wrong")
    with pytest.raises(MigrationRefused, match="本地测试库"):
        private_target("postgresql://user:local@127.0.0.1/test_fixture")
    assert private_target("postgresql://user:local@127.0.0.1/test_fixture", allow_loopback=True).drivername == "postgresql+psycopg"
    assert private_target("postgresql://user:secret@db.example.com/joblens_private?sslmode=verify-full").database == "joblens_private"


def test_sqlite_backup_includes_committed_wal_and_snapshot_is_read_only(tmp_path: Path):
    path = tmp_path / "source.db"
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA journal_mode = WAL").fetchone() == ("wal",)
        db.execute("CREATE TABLE unit (id INTEGER PRIMARY KEY, name TEXT)")
        db.execute("INSERT INTO unit VALUES (42, 'synthetic')")
        db.commit()
        with open_snapshot(path) as snapshot:
            assert snapshot.exec_driver_sql("SELECT COUNT(*) FROM unit").scalar_one() == 1
            db.execute("INSERT INTO unit VALUES (43, 'after snapshot')")
            db.commit()
            assert snapshot.exec_driver_sql("SELECT COUNT(*) FROM unit").scalar_one() == 1
            with pytest.raises(OperationalError, match="readonly"):
                snapshot.exec_driver_sql("DELETE FROM unit")


def test_fingerprints_compare_utc_instants_and_order_independent_json():
    plain = datetime(2026, 1, 1, 8)
    zoned = datetime(2026, 1, 1, 16, tzinfo=timezone(timedelta(hours=8)))
    assert fingerprint({"time": plain, "json": {"b": 1, "a": 2}}) == fingerprint({"json": {"a": 2, "b": 1}, "time": zoned})
    assert fingerprint({"time": plain}) != fingerprint({"time": zoned.replace(day=2)})
