"""External Collector contracts and internal normalized import DTOs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.jobs import RemoteConfidence, RemoteStatus


class CollectorReportEnvelope(BaseModel):
    """Versioned report envelope emitted by the browser Collector.

    Jobs remain untyped at the envelope level so a malformed item can be
    recorded as an item-level issue without rejecting the entire report.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    version: str = Field(min_length=1)
    generated_at: datetime = Field(alias="generatedAt")
    config: dict[str, Any] = Field(default_factory=dict)
    statistics: dict[str, Any] = Field(default_factory=dict)
    jobs: list[Any]
    candidates: list[Any] = Field(default_factory=list)


class CollectorJobV131(BaseModel):
    """Known fields from the JobLens Collector v1.3.1 job record.

    Unknown fields are deliberately retained by Pydantic and the adapter also
    keeps the untouched raw dictionary as source evidence.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    title: str
    company: str
    url: str

    area: str | None = None
    salary_min_k: float | None = Field(default=None, alias="salaryMinK")
    salary_max_k: float | None = Field(default=None, alias="salaryMaxK")
    experience: str | None = None
    education: str | None = None
    description: str | None = None
    skills: list[str] = Field(default_factory=list)

    remote_status: RemoteStatus | None = Field(default=None, alias="remoteStatus")
    remote_confidence: RemoteConfidence | None = Field(
        default=None, alias="remoteConfidence"
    )
    remote_matched: bool | None = Field(default=None, alias="remoteMatched")

    collected_at: datetime | None = Field(default=None, alias="collectedAt")
    first_seen_at: datetime | None = Field(default=None, alias="firstSeenAt")
    last_seen_at: datetime | None = Field(default=None, alias="lastSeenAt")

    raw_text: str | None = Field(default=None, alias="rawText")
    detail_text: str | None = Field(default=None, alias="detailText")
    source_job_id: str | None = Field(default=None, alias="sourceJobId")

    @field_validator("salary_min_k", "salary_max_k", mode="before")
    @classmethod
    def validate_salary_number(cls, value: Any) -> Any:
        """Reject booleans and numeric strings instead of silently coercing them."""

        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("salary values must be JSON numbers")
        if value < 0:
            raise ValueError("salary values must be non-negative")
        return float(value)


@dataclass(frozen=True, slots=True)
class ImportIssue:
    """A report- or item-level problem that can later become JobImportItem."""

    stage: Literal["adapter", "normalizer"]
    code: str
    message: str
    index: int | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AdaptedCollectorJob:
    """One version-specific external job after structural validation."""

    index: int
    source_version: str
    report_generated_at: datetime
    job: CollectorJobV131
    source_raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AdaptedCollectorReport:
    """Collector report converted into version-specific validated records."""

    source_version: str
    generated_at: datetime
    config: dict[str, Any]
    statistics: dict[str, Any]
    jobs: tuple[AdaptedCollectorJob, ...]
    issues: tuple[ImportIssue, ...]
    candidates_raw: tuple[Any, ...]

    @property
    def received(self) -> int:
        return len(self.jobs) + len(self.issues)

    @property
    def candidate_count(self) -> int:
        return len(self.candidates_raw)


@dataclass(frozen=True, slots=True)
class NormalizedJobInput:
    """Version-agnostic input for the future repository/use-case layer."""

    source: str
    source_version: str
    source_job_id: str | None
    source_url: str
    normalized_source_url: str
    source_raw: dict[str, Any]

    canonical_key: str
    canonical_key_version: str

    title: str
    company: str
    area: str | None
    salary_min_k: float | None
    salary_max_k: float | None
    experience: str | None
    education: str | None
    description: str | None
    skills: tuple[str, ...]
    remote_status: RemoteStatus
    remote_confidence: RemoteConfidence

    collected_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
    input_index: int = 0


@dataclass(frozen=True, slots=True)
class NormalizedCollectorReport:
    """Normalized jobs plus all non-fatal issues from both pipeline stages."""

    source_version: str
    generated_at: datetime
    config: dict[str, Any]
    statistics: dict[str, Any]
    jobs: tuple[NormalizedJobInput, ...]
    issues: tuple[ImportIssue, ...]
    candidates_raw: tuple[Any, ...]

    @property
    def received(self) -> int:
        return len(self.jobs) + len(self.issues)

    @property
    def candidate_count(self) -> int:
        return len(self.candidates_raw)
