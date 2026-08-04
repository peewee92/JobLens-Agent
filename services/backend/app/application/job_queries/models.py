"""Application read models and query inputs for the Job Pool."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.jobs import RemoteConfidence, RemoteStatus


class JobSort(StrEnum):
    LATEST = "latest"
    SALARY_DESC = "salaryDesc"
    SALARY_ASC = "salaryAsc"


@dataclass(frozen=True, slots=True)
class JobListQuery:
    q: str | None = None
    city: str | None = None
    min_salary_k: float | None = None
    remote_status: RemoteStatus | None = None
    source: str | None = None
    limit: int = 20
    offset: int = 0
    sort: JobSort = JobSort.LATEST


@dataclass(frozen=True, slots=True)
class JobListItem:
    id: str
    title: str
    company: str
    area: str | None
    salary_min_k: float | None
    salary_max_k: float | None
    remote_status: RemoteStatus
    remote_confidence: RemoteConfidence
    source: str
    source_url: str
    source_version: str | None
    collected_at: datetime | None


@dataclass(frozen=True, slots=True)
class JobDetail:
    id: str
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
    source: str
    source_url: str
    source_version: str | None
    description_quality: str | None
    requirement_review_eligible: bool | None
    requirement_review_ineligibility_reasons: tuple[str, ...]
    collected_at: datetime | None


@dataclass(frozen=True, slots=True)
class JobPage:
    total: int
    limit: int
    offset: int
    items: tuple[JobListItem, ...]
