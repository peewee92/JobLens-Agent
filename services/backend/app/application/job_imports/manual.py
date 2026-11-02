"""Thin, explicit provenance adapter for pasted postings, not a Collector report."""
from datetime import UTC, datetime
from hashlib import sha256
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.application.job_imports.canonical_key import build_canonical_key, normalize_source_url
from app.application.job_imports.models import NormalizedCollectorReport, NormalizedJobInput
from app.domain.jobs import RemoteConfidence, RemoteStatus


class ManualJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=50000)
    source_url: str | None = Field(default=None, alias="sourceUrl", max_length=2048)

    @field_validator("title", "company", mode="before")
    @classmethod
    def trim_label(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("description")
    @classmethod
    def preserve_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must contain posting text")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        value = value.strip()
        # Validation only: the application never fetches the supplied URL.
        normalize_source_url(value, source="manual")
        return value


def normalize_manual_job(job: ManualJobInput) -> NormalizedCollectorReport:
    now = datetime.now(UTC)
    raw = job.model_dump(by_alias=True)
    raw["provenanceKind"] = "user_paste"
    normalized_url = normalize_source_url(job.source_url, source="manual") if job.source_url else None
    # A local content identity, not an ID allegedly assigned by a hiring platform.
    local_id = None if normalized_url else "paste-" + sha256(
        json.dumps([job.title, job.company, job.description], ensure_ascii=False).encode()
    ).hexdigest()
    normalized = NormalizedJobInput(
        source="manual", source_version="manual-paste-v1", source_job_id=local_id,
        source_url=job.source_url or "", normalized_source_url=normalized_url, source_raw=raw,
        canonical_key=build_canonical_key(source="manual", source_job_id=local_id,
            normalized_source_url=normalized_url, company=job.company, title=job.title, area=None),
        canonical_key_version="v1", title=job.title, company=job.company, area=None,
        salary_min_k=None, salary_max_k=None, experience=None, education=None,
        description=job.description, skills=(), remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW, collected_at=now, first_seen_at=now, last_seen_at=now,
    )
    return NormalizedCollectorReport(
        source_version="manual-paste-v1", generated_at=now, config={},
        statistics={"provenanceKind": "user_paste"}, jobs=(normalized,), issues=(), candidates_raw=(),
    )
