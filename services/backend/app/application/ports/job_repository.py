"""Repository port for the P0-1 job import application slice.

This module belongs to the application layer. It describes the persistence
capabilities the use case needs without exposing SQLAlchemy models or Session.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.application.job_imports.models import NormalizedJobInput
from app.domain.jobs import ImportOutcome


class RepositoryRecordNotFound(LookupError):
    """Raised when an update targets a record that no longer exists."""


@dataclass(frozen=True, slots=True)
class JobSourceRef:
    """Minimal source identity needed by the application decision logic."""

    id: str
    job_id: str


@dataclass(frozen=True, slots=True)
class JobImportWrite:
    """Data required to create one import-batch audit record."""

    source_version: str
    collector_version: str | None = None
    received: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: tuple[dict[str, Any], ...] = ()
    search_intent_snapshot: dict[str, Any] = field(default_factory=dict)
    source_snapshot: dict[str, Any] = field(default_factory=dict)
    collected_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class JobImportItemWrite:
    """Data required to append one per-input import result."""

    import_id: str
    input_index: int
    outcome: ImportOutcome
    job_id: str | None = None
    job_source_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class AbstractJobRepository(ABC):
    """Persistence operations needed by the future ImportJobs use case.

    Implementations may flush so generated IDs and constraints are available
    inside the current transaction, but they must never commit or rollback.
    Transaction ownership belongs to the Unit of Work / application use case.
    """

    @abstractmethod
    def find_job_id_by_canonical_key(self, canonical_key: str) -> str | None:
        """Return the JobLens job ID for an idempotency key, if present."""

    @abstractmethod
    def find_source_by_external_id(
        self, source: str, source_job_id: str
    ) -> JobSourceRef | None:
        """Find source identity by platform-scoped external identifier."""

    @abstractmethod
    def find_source_by_normalized_url(
        self, source: str, normalized_source_url: str
    ) -> JobSourceRef | None:
        """Find source identity by the stable normalized source URL."""

    @abstractmethod
    def add_job(self, data: NormalizedJobInput) -> str:
        """Add a normalized Job and flush so its generated ID is available."""

    @abstractmethod
    def update_job(self, job_id: str, data: NormalizedJobInput) -> None:
        """Update mutable normalized fields without changing Job identity."""

    @abstractmethod
    def add_source(self, job_id: str, data: NormalizedJobInput) -> str:
        """Add external source evidence and flush its generated ID."""

    @abstractmethod
    def update_source(self, source_id: str, data: NormalizedJobInput) -> None:
        """Refresh source evidence while preserving first-seen history."""

    @abstractmethod
    def add_import(self, data: JobImportWrite) -> str:
        """Create one import-batch audit row and return its ID."""

    @abstractmethod
    def update_import_summary(
        self,
        import_id: str,
        *,
        created: int,
        updated: int,
        skipped: int,
        errors: tuple[dict[str, Any], ...],
    ) -> None:
        """Write final counters for an import batch before commit."""

    @abstractmethod
    def add_import_item(self, data: JobImportItemWrite) -> str:
        """Append one per-input audit result and return its ID."""
