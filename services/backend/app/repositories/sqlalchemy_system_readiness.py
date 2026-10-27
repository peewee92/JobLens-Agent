"""Infrastructure-only, read-only schema readiness adapter."""
from pathlib import Path
from urllib.parse import unquote

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.application.system_readiness import CheckStatus, ReadinessCode, SystemReadiness
from app.db.base import Base
import app.db.models  # noqa: F401 -- register all required tables


class SystemReadinessProbe:
    def __init__(self, engine: Engine, migration_directory: Path | None = None):
        self._engine = engine
        self._migration_directory = migration_directory or Path(__file__).resolve().parents[2] / "alembic"

    def execute(self) -> SystemReadiness:
        # SQLite can create a file even for a SELECT; fail before connecting.
        url = self._engine.url
        if url.get_backend_name() == "sqlite":
            database = url.database or ""
            if database not in ("", ":memory:", "file::memory:") and url.query.get("mode") != "memory":
                path = unquote(database[5:].split("?", 1)[0]) if database.startswith("file:") else database
                if not Path(path).is_file():
                    return SystemReadiness(False, "database_unavailable", "failed")

        try:
            required = tuple(sorted(ScriptDirectory(str(self._migration_directory)).get_heads()))
            if not required:
                raise ValueError("No migration heads")
        except Exception:
            # Migration loading can fail with configuration or Python import
            # errors. Fail closed without publishing paths or connection data.
            return SystemReadiness(False, "migration_metadata_unavailable", "unknown")

        try:
            with self._engine.connect() as connection:
                current = tuple(sorted(MigrationContext.configure(connection).get_current_heads()))
                present = set(inspect(connection).get_table_names())
        except SQLAlchemyError:
            return SystemReadiness(False, "database_unavailable", "failed", required_revisions=required)

        missing = tuple(sorted(set(Base.metadata.tables) - present))
        migrations: CheckStatus = "passed" if current == required else "failed"
        tables: CheckStatus = "failed" if missing else "passed"
        code: ReadinessCode = (
            "migration_required" if migrations == "failed"
            else "schema_incomplete" if missing else "ready"
        )
        return SystemReadiness(code == "ready", code, "passed", migrations, tables, current, required, missing)
