"""Back up a SQLite source read-only, migrate ONLY a new copy, verify old rows.

Usage: python -m scripts.verify_migration_copy --source /abs/source.db --output /abs/new-copy.db
Neither an existing output nor the source is ever overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from app.repositories.sqlalchemy_system_readiness import SystemReadinessProbe

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _snapshot(connection: sqlite3.Connection, columns_by_table: dict[str, list[str]]) -> dict[str, tuple[int, str]]:
    result = {}
    for table, columns in columns_by_table.items():
        selected = ",".join(_quote(column) for column in columns)
        digest = hashlib.sha256()
        count = 0
        for row in connection.execute(f"SELECT {selected} FROM {_quote(table)} ORDER BY {selected}"):
            digest.update(repr(tuple(row)).encode("utf-8"))
            digest.update(b"\n")
            count += 1
        result[table] = (count, digest.hexdigest())
    return result


def verify_copy(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if not source.is_file():
        raise ValueError("Source database does not exist")
    if source == output or output.exists():
        raise ValueError("Output must be a new file, never the source or an existing backup")
    # Exclusive creation also protects against concurrent invocations.
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(output) as copy:
            original.backup(copy)

    with sqlite3.connect(output.as_uri() + "?mode=ro", uri=True) as copy:
        if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup integrity check failed; source was not changed")
        tables = [row[0] for row in copy.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' ORDER BY name"
        )]
        columns = {table: [row[1] for row in copy.execute(f"PRAGMA table_info({_quote(table)})")] for table in tables}
        before = _snapshot(copy, columns)

    url = URL.create("sqlite", database=str(output)).render_as_string(hide_password=False)
    env = {**os.environ, "DATABASE_URL": url, "OPENAI_API_KEY": "", "APP_ENV": "test"}
    for prefix in ("PROFILE_EXTRACTOR", "REQUIREMENT_EXTRACTOR", "SEMANTIC_MATCH", "CAREER_INTENT", "REQUIREMENT_EXTRACTOR_FALLBACK"):
        env[f"{prefix}_PROVIDER"] = "disabled"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_ROOT, env=env, check=True)

    with sqlite3.connect(output.as_uri() + "?mode=ro", uri=True) as copy:
        after = _snapshot(copy, columns)
        intact = copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        foreign_keys_ok = not copy.execute("PRAGMA foreign_key_check").fetchall()
    engine = create_engine(url)
    try:
        readiness = SystemReadinessProbe(engine).execute()
    finally:
        engine.dispose()
    preserved = before == after
    if not (preserved and intact and foreign_keys_ok and readiness.ready):
        raise ValueError("Copy validation failed; keep the source unchanged and inspect the copy")
    return {
        "ready": True, "existingRowsPreserved": True, "integrityOk": True,
        "foreignKeysOk": True, "verifiedExistingTables": len(tables),
        "requiredRevisions": list(readiness.required_revisions),
        "sourceOpenedReadOnly": True, "providersDisabledForMigration": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify_copy(args.source, args.output)
    except (ValueError, OSError, sqlite3.Error, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Validation failed: {error}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
