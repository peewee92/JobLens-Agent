"""Version-agnostic normalization for adapted Collector jobs."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import re
import unicodedata

from app.application.job_imports.canonical_key import (
    CANONICAL_KEY_VERSION,
    build_canonical_key,
    extract_source_job_id,
    normalize_external_id,
    normalize_source_url,
)
from app.application.job_imports.errors import (
    CanonicalIdentityError,
    JobNormalizationError,
)
from app.application.job_imports.models import (
    AdaptedCollectorJob,
    AdaptedCollectorReport,
    ImportIssue,
    NormalizedCollectorReport,
    NormalizedJobInput,
)
from app.domain.jobs import RemoteConfidence, RemoteStatus

SOURCE_NAME = "boss"


def _normalize_short_text(
    value: str | None,
    *,
    field: str,
    max_length: int,
    required: bool = False,
) -> str | None:
    if value is None:
        if required:
            raise JobNormalizationError(f"missing_{field}", f"{field} is required")
        return None

    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        if required:
            raise JobNormalizationError(f"missing_{field}", f"{field} is required")
        return None
    if len(normalized) > max_length:
        raise JobNormalizationError(
            f"{field}_too_long",
            f"{field} exceeds maximum length {max_length}",
        )
    return normalized


def _normalize_description(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n")).strip()
    return normalized or None


def _normalize_skills(values: list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()

    for raw_value in values:
        value = _normalize_short_text(
            raw_value,
            field="skill",
            max_length=100,
            required=False,
        )
        if value is None:
            continue
        identity = value.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        normalized.append(value)

    if len(normalized) > 128:
        raise JobNormalizationError(
            "too_many_skills", "skills exceeds maximum item count 128"
        )
    return tuple(normalized)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_remote_status(
    status: RemoteStatus | None,
    matched: bool | None,
) -> RemoteStatus:
    if status is not None:
        return status
    if matched is True:
        return RemoteStatus.CONFIRMED
    # A missing/false marker is not proof that remote work was explicitly rejected.
    return RemoteStatus.UNKNOWN


def normalize_adapted_job(record: AdaptedCollectorJob) -> NormalizedJobInput:
    """Convert one version-specific job into the stable internal import shape."""

    job = record.job
    title = _normalize_short_text(
        job.title, field="title", max_length=255, required=True
    )
    company = _normalize_short_text(
        job.company, field="company", max_length=255, required=True
    )
    assert title is not None
    assert company is not None

    source_url = job.url.strip()
    if len(source_url) > 2048:
        raise JobNormalizationError(
            "source_url_too_long", "source URL exceeds maximum length 2048"
        )

    try:
        normalized_source_url = normalize_source_url(source_url, source=SOURCE_NAME)
    except CanonicalIdentityError as error:
        raise JobNormalizationError("invalid_source_url", str(error)) from error

    explicit_source_job_id = normalize_external_id(job.source_job_id)
    url_source_job_id = extract_source_job_id(
        normalized_source_url, source=SOURCE_NAME
    )
    if (
        explicit_source_job_id is not None
        and url_source_job_id is not None
        and explicit_source_job_id != url_source_job_id
    ):
        raise JobNormalizationError(
            "source_identity_mismatch",
            "sourceJobId does not match the job ID encoded in source URL",
        )
    source_job_id = explicit_source_job_id or url_source_job_id
    if source_job_id is not None and len(source_job_id) > 255:
        raise JobNormalizationError(
            "source_job_id_too_long",
            "source job ID exceeds maximum length 255",
        )

    area = _normalize_short_text(job.area, field="area", max_length=255)
    experience = _normalize_short_text(
        job.experience, field="experience", max_length=100
    )
    education = _normalize_short_text(
        job.education, field="education", max_length=100
    )

    salary_min_k = job.salary_min_k
    salary_max_k = job.salary_max_k
    if (
        salary_min_k is not None
        and salary_max_k is not None
        and salary_max_k < salary_min_k
    ):
        raise JobNormalizationError(
            "invalid_salary_range",
            "salaryMaxK must be greater than or equal to salaryMinK",
        )

    collected_at = _as_utc(job.collected_at or record.report_generated_at)
    first_seen_at = _as_utc(job.first_seen_at or collected_at)
    last_seen_at = _as_utc(job.last_seen_at or collected_at)
    if last_seen_at < first_seen_at:
        raise JobNormalizationError(
            "invalid_seen_range",
            "lastSeenAt must be greater than or equal to firstSeenAt",
        )

    try:
        canonical_key = build_canonical_key(
            source=SOURCE_NAME,
            source_job_id=source_job_id,
            normalized_source_url=normalized_source_url,
            company=company,
            title=title,
            area=area,
        )
    except CanonicalIdentityError as error:
        raise JobNormalizationError("canonical_identity_error", str(error)) from error

    return NormalizedJobInput(
        source=SOURCE_NAME,
        source_version=record.source_version,
        source_job_id=source_job_id,
        source_url=source_url,
        normalized_source_url=normalized_source_url,
        source_raw=deepcopy(record.source_raw),
        canonical_key=canonical_key,
        canonical_key_version=CANONICAL_KEY_VERSION,
        title=title,
        company=company,
        area=area,
        salary_min_k=salary_min_k,
        salary_max_k=salary_max_k,
        experience=experience,
        education=education,
        description=_normalize_description(job.description),
        skills=_normalize_skills(job.skills),
        remote_status=_normalize_remote_status(
            job.remote_status, job.remote_matched
        ),
        remote_confidence=job.remote_confidence or RemoteConfidence.LOW,
        collected_at=collected_at,
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        input_index=record.index,
    )


def normalize_adapted_report(
    report: AdaptedCollectorReport,
) -> NormalizedCollectorReport:
    """Normalize all valid adapted jobs while preserving item-level issues."""

    jobs: list[NormalizedJobInput] = []
    issues = list(report.issues)

    for record in report.jobs:
        try:
            jobs.append(normalize_adapted_job(record))
        except JobNormalizationError as error:
            issues.append(
                ImportIssue(
                    stage="normalizer",
                    index=record.index,
                    code=error.code,
                    message=str(error),
                    raw=deepcopy(record.source_raw),
                )
            )

    return NormalizedCollectorReport(
        source_version=report.source_version,
        generated_at=report.generated_at,
        config=deepcopy(report.config),
        statistics=deepcopy(report.statistics),
        jobs=tuple(jobs),
        issues=tuple(issues),
        candidates_raw=tuple(deepcopy(report.candidates_raw)),
    )
