"""Version-specific Collector report adapters."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from pydantic import ValidationError

from app.application.job_imports.errors import (
    InvalidCollectorReportError,
    UnsupportedCollectorVersionError,
)
from app.application.job_imports.models import (
    AdaptedCollectorJob,
    AdaptedCollectorReport,
    CollectorJobV131,
    CollectorReportEnvelope,
    ImportIssue,
)

SUPPORTED_COLLECTOR_VERSIONS = frozenset({"1.3.1", "1.4.0"})


def _format_validation_error(error: ValidationError) -> str:
    parts: list[str] = []
    for item in error.errors(include_url=False)[:3]:
        location = ".".join(str(part) for part in item.get("loc", ())) or "payload"
        parts.append(f"{location}: {item.get('msg', 'invalid value')}")
    return "; ".join(parts)


def adapt_collector_report(payload: Mapping[str, Any]) -> AdaptedCollectorReport:
    """Validate a Collector report envelope and adapt supported Collector jobs.

    Envelope failures stop the batch because version/config/jobs cannot be
    trusted. Individual malformed job records become non-fatal issues so a
    future import use case can continue with the remaining records.
    """

    try:
        envelope = CollectorReportEnvelope.model_validate(payload)
    except ValidationError as error:
        raise InvalidCollectorReportError(_format_validation_error(error)) from error

    if envelope.version not in SUPPORTED_COLLECTOR_VERSIONS:
        raise UnsupportedCollectorVersionError(
            f"unsupported Collector version: {envelope.version}"
        )

    jobs: list[AdaptedCollectorJob] = []
    issues: list[ImportIssue] = []

    for index, raw_item in enumerate(envelope.jobs):
        if not isinstance(raw_item, Mapping):
            issues.append(
                ImportIssue(
                    stage="adapter",
                    index=index,
                    code="invalid_job_type",
                    message="job item must be a JSON object",
                )
            )
            continue

        source_raw = deepcopy(dict(raw_item))
        try:
            collector_job = CollectorJobV131.model_validate(raw_item)
        except ValidationError as error:
            issues.append(
                ImportIssue(
                    stage="adapter",
                    index=index,
                    code="invalid_job_payload",
                    message=_format_validation_error(error),
                    raw=source_raw,
                )
            )
            continue

        jobs.append(
            AdaptedCollectorJob(
                index=index,
                source_version=envelope.version,
                report_generated_at=envelope.generated_at,
                job=collector_job,
                source_raw=source_raw,
            )
        )

    return AdaptedCollectorReport(
        source_version=envelope.version,
        generated_at=envelope.generated_at,
        config=deepcopy(envelope.config),
        statistics=deepcopy(envelope.statistics),
        jobs=tuple(jobs),
        issues=tuple(issues),
        candidates_raw=tuple(deepcopy(envelope.candidates)),
    )
