"""Read-only runtime facts used by Requirement acceptance readiness."""
from __future__ import annotations

from pathlib import Path
import sqlite3

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def requirement_acceptance_migration_head(*, backend_root: Path) -> str:
    """Return the current Alembic head without mutating the database."""

    root = backend_root.resolve()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:  # pragma: no cover - defensive migration invariant
        raise RuntimeError("Alembic does not have a current head revision")
    return head


def read_requirement_acceptance_database_revision(
    database_url: str,
    *,
    backend_root: Path,
) -> tuple[bool, str | None, str | None]:
    """Read the configured database revision without creating or upgrading it."""

    url = make_url(database_url)
    if url.drivername.startswith("sqlite"):
        if not url.database or url.database == ":memory:":
            return False, None, "Readiness requires a persistent SQLite database file."
        database_path = Path(url.database)
        if not database_path.is_absolute():
            database_path = (backend_root.resolve() / database_path).resolve()
        if not database_path.exists():
            return False, None, f"SQLite database file does not exist: {database_path}"
        try:
            with sqlite3.connect(
                f"file:{database_path}?mode=ro",
                uri=True,
            ) as connection:
                table = connection.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name='alembic_version'"
                ).fetchone()
                if table is None:
                    return True, None, "Database has no alembic_version table."
                row = connection.execute(
                    "SELECT version_num FROM alembic_version LIMIT 1"
                ).fetchone()
                return True, row[0] if row is not None else None, None
        except sqlite3.Error as error:
            return False, None, (
                f"SQLite read-only check failed: {type(error).__name__}"
            )

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
            return True, revision, None
    except Exception as error:  # external database adapters vary
        return False, None, f"Database read check failed: {type(error).__name__}"
    finally:
        engine.dispose()
