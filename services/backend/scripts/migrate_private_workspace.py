"""Copy personal workspace records, never the SQLite file, to an empty private PostgreSQL database."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any, Iterator

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Table, create_engine, func, inspect, select, text
from sqlalchemy.engine import URL, make_url

from app.cloud.postgres import verified_postgres
from app.db.base import Base
import app.db.models  # noqa: F401 -- register tables before selecting a copy order

BUSINESS_TABLES = frozenset({
    "user_profiles", "profile_evidence", "profile_skills", "profile_skill_evidence", "search_intents",
    "jobs", "job_sources", "job_imports", "job_import_candidates", "job_import_items",
    "job_requirement_extractions", "job_requirements", "job_requirement_confirmations", "trace_spans",
    "match_reports", "user_feedback", "career_agent_runs", "career_agent_run_events",
    "application_workspaces", "execution_action_items", "resume_variants",
    "application_timeline_events", "evidence_proposals", "analysis_execution_receipts",
})
TARGET_ENV = "JOBLENS_MIGRATION_DATABASE_URL"
MIGRATIONS = Path(__file__).resolve().parents[1] / "alembic"
BATCH = 200


class MigrationRefused(ValueError):
    """Safe operator feedback; never include a connection URL or row values."""


def ordered_tables() -> list[Table]:
    tables = [table for table in Base.metadata.sorted_tables if table.name in BUSINESS_TABLES]
    if {t.name for t in tables} != BUSINESS_TABLES or any(
        fk.column.table.name not in BUSINESS_TABLES for t in tables for fk in t.foreign_keys
    ):
        raise MigrationRefused("业务表或依赖已变更，请核对迁移范围后再执行。")
    return tables


def private_target(raw: str, *, allow_loopback: bool = False) -> URL:
    try:
        url = make_url(raw)
    except Exception:
        raise MigrationRefused("无法识别 PostgreSQL 连接配置。") from None
    if (url.drivername not in {"postgresql", "postgresql+psycopg"} or not url.host or not url.database
            or not url.username or url.database in {"postgres", "template0", "template1"} or "-pooler." in url.host.lower()):
        raise MigrationRefused("请填写独立私人工作库的 PostgreSQL 直连地址，不要选系统库。")
    # Do not allow libpq options to override the verified host, database, or search path.
    if set(url.query) - {"sslmode", "channel_binding", "connect_timeout"}:
        raise MigrationRefused("连接配置含未支持的参数；请使用私人工作库的直连地址。")
    loopback = url.host in {"127.0.0.1", "::1"}
    if (loopback and not allow_loopback) or (not loopback and url.query.get("sslmode") != "verify-full"):
        raise MigrationRefused("云库必须用 sslmode=verify-full；只有独立的本地测试库允许显式跳过。")
    url = url.set(drivername="postgresql+psycopg")
    return url if loopback else verified_postgres(url)


@contextmanager
def open_snapshot(source_path: Path) -> Iterator[Connection]:
    source_path = source_path.resolve(strict=True)
    if not source_path.is_file():
        raise MigrationRefused("源必须是本地 SQLite 数据库文件。")
    with tempfile.TemporaryDirectory(prefix="joblens-private-copy-") as directory:
        snapshot = Path(directory) / "snapshot.db"
        # SQLite's online backup includes committed WAL contents; never copy the live file directly.
        with closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True, timeout=10)) as original, \
                closing(sqlite3.connect(snapshot)) as copy:
            original.backup(copy)
            if copy.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise MigrationRefused("源副本完整性检查未通过。")
            if copy.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise MigrationRefused("源副本存在缺失的关联记录，请先在另一个副本中修复。")
        engine = create_engine("sqlite+pysqlite://", creator=lambda: sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True))
        try:
            with engine.connect() as connection:
                yield connection
        finally:
            engine.dispose()


def assert_schema(connection: Connection) -> None:
    expected = set(ScriptDirectory(str(MIGRATIONS)).get_heads())
    if set(MigrationContext.configure(connection).get_current_heads()) != expected:
        raise MigrationRefused("请先备份并将源副本／目标库升级到当前 Alembic 版本。")
    inspector = inspect(connection)
    for table in ordered_tables():
        if not inspector.has_table(table.name) or not {c.name for c in table.c} <= {
            c["name"] for c in inspector.get_columns(table.name)
        }:
            raise MigrationRefused(f"业务表结构不完整：{table.name}。")


def row_batches(connection: Connection, table: Table, *, redact_traces: bool) -> Iterator[list[dict[str, Any]]]:
    stmt = select(table)
    if redact_traces and table.name == "trace_spans":
        extract = Base.metadata.tables["job_requirement_extractions"]
        stmt = stmt.where(table.c.id.in_(select(extract.c.trace_run_id)))
    with connection.execute(stmt).mappings() as result:
        for batch in result.partitions(BATCH):
            rows = [dict(row) for row in batch]
            if redact_traces and table.name == "trace_spans":
                # Requirement history needs these foreign keys, not raw provider output, errors or prompt inputs.
                for row in rows:
                    row.update(input_refs={}, output=None, error=None)
            yield rows


def counts(source: Connection) -> dict[str, int]:
    assert_schema(source)
    return {table.name: sum(len(batch) for batch in row_batches(source, table, redact_traces=True))
            for table in ordered_tables()}


def fingerprint(row: dict[str, Any]) -> bytes:
    def normalize(value: Any) -> str:
        if isinstance(value, datetime):
            return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
        return str(value)
    encoded = json.dumps(row, default=normalize, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).digest()


def copy_workspace(source: Connection, target: Connection, database_name: str) -> dict[str, int]:
    """Caller owns the target transaction. Works only on an empty isolated database."""
    assert_schema(source)
    if target.dialect.name != "postgresql" or target.execute(text("SELECT current_database()")).scalar_one() != database_name:
        raise MigrationRefused("已连接的数据库与指定的私人工作库不一致。")
    assert_schema(target)
    tables = ordered_tables()
    guard_tables = list(Base.metadata.sorted_tables)
    # A concurrent writer cannot create rows between the empty check and the import.
    qualified = ", ".join(target.dialect.identifier_preparer.quote(t.name) for t in guard_tables)
    target.exec_driver_sql("LOCK TABLE " + qualified + " IN SHARE ROW EXCLUSIVE MODE")
    if any(target.execute(select(func.count()).select_from(t)).scalar_one() for t in guard_tables):
        raise MigrationRefused("目标库已有数据，停止以免覆盖或合并到错误账号。")
    copied: dict[str, int] = {}
    for table in tables:
        before: Counter[bytes] = Counter()
        for batch in row_batches(source, table, redact_traces=True):
            target.execute(table.insert(), batch)
            before.update(map(fingerprint, batch))
        after = Counter(fingerprint(row) for batch in row_batches(target, table, redact_traces=False) for row in batch)
        if before != after:
            raise MigrationRefused(f"逐行核验未通过，迁移已回滚：{table.name}。")
        copied[table.name] = sum(before.values())

    # Explicitly copied integer IDs don't advance serial sequences.
    for table in tables:
        serial_column = table.autoincrement_column
        if serial_column is None or not copied[table.name]:
            continue
        sequence = target.execute(text("SELECT pg_get_serial_sequence(:table, :column)"),
                                  {"table": table.name, "column": serial_column.name}).scalar_one()
        if sequence:
            maximum = target.execute(select(func.max(serial_column))).scalar_one()
            if maximum > 0:
                target.execute(text("SELECT setval(CAST(:sequence AS regclass), :maximum, true)"),
                               {"sequence": sequence, "maximum": maximum})
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="default is a local-only dry run")
    parser.add_argument("--expected-database")
    parser.add_argument("--allow-loopback-test-target", action="store_true")
    args = parser.parse_args()
    try:
        with open_snapshot(args.source) as source:
            if args.apply:
                if not args.expected_database or not os.environ.get(TARGET_ENV):
                    raise MigrationRefused(f"请指定 --expected-database，并通过 {TARGET_ENV} 配置连接。")
                url = private_target(os.environ[TARGET_ENV], allow_loopback=args.allow_loopback_test_target)
                if url.database != args.expected_database:
                    raise MigrationRefused("连接配置的库名与预期不符。")
                engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 10})
                try:
                    with engine.begin() as target:
                        result = copy_workspace(source, target, args.expected_database)
                finally:
                    engine.dispose()
            else:
                result = counts(source)
        print(json.dumps({"applied": args.apply, "rows": result}, ensure_ascii=False, sort_keys=True))
        return 0
    except MigrationRefused as error:
        print(f"迁移停止：{error}", file=sys.stderr)
        return 2
    except Exception as error:
        # Driver errors can contain passwords, SQL parameters, or resume text.
        print(f"迁移未完成（{type(error).__name__}）。请检查连接和源库状态；未输出个人数据。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
