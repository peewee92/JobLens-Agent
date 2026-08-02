"""Read models for completed Job Import audit details."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.jobs import ImportOutcome


@dataclass(frozen=True, slots=True)
class JobImportErrorDetail:
    index: int
    stage: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class JobImportItemDetail:
    input_index: int
    outcome: ImportOutcome
    job_id: str | None
    job_source_id: str | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class JobImportDetail:
    import_id: str
    source_version: str
    collector_version: str | None
    received: int
    created: int
    updated: int
    skipped: int
    errors: tuple[JobImportErrorDetail, ...]
    search_intent_snapshot: dict[str, Any]
    source_snapshot: dict[str, Any]
    collected_at: datetime | None
    created_at: datetime
    items: tuple[JobImportItemDetail, ...]
