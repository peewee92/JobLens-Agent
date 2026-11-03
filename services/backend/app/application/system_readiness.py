"""Read-only deployment readiness; never runs migrations or creates databases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CheckStatus = Literal["passed", "failed", "unknown"]
ReadinessCode = Literal[
    "ready", "database_unavailable", "migration_required", "schema_incomplete",
    "migration_metadata_unavailable",
]


@dataclass(frozen=True)
class SystemReadiness:
    ready: bool
    code: ReadinessCode
    database: CheckStatus
    migrations: CheckStatus = "unknown"
    tables: CheckStatus = "unknown"
    current_revisions: tuple[str, ...] = ()
    required_revisions: tuple[str, ...] = ()
    missing_tables: tuple[str, ...] = ()
