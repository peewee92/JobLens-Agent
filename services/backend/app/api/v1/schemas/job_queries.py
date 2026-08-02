"""HTTP response contracts for Job Pool list and detail APIs."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from app.api.v1.schemas.common import CamelCaseModel
from app.application.job_queries import JobDetail, JobListItem, JobPage
from app.domain.jobs import RemoteConfidence, RemoteStatus


class JobListItemResponse(CamelCaseModel):
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

    @classmethod
    def from_item(cls, item: JobListItem) -> "JobListItemResponse":
        return cls(**asdict(item))


class JobDetailResponse(JobListItemResponse):
    experience: str | None
    education: str | None
    description: str | None
    skills: list[str]

    @classmethod
    def from_detail(cls, detail: JobDetail) -> "JobDetailResponse":
        return cls(
            id=detail.id,
            title=detail.title,
            company=detail.company,
            area=detail.area,
            salary_min_k=detail.salary_min_k,
            salary_max_k=detail.salary_max_k,
            experience=detail.experience,
            education=detail.education,
            description=detail.description,
            skills=list(detail.skills),
            remote_status=detail.remote_status,
            remote_confidence=detail.remote_confidence,
            source=detail.source,
            source_url=detail.source_url,
            source_version=detail.source_version,
            collected_at=detail.collected_at,
        )


class JobListResponse(CamelCaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobListItemResponse]

    @classmethod
    def from_page(cls, page: JobPage) -> "JobListResponse":
        return cls(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            items=[JobListItemResponse.from_item(item) for item in page.items],
        )
