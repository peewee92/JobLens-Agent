"""Pure job-import boundary and normalization helpers.

This package intentionally does not persist data. It converts external Collector
payloads into stable internal inputs that a later use case can store through a
repository.
"""

from app.application.job_imports.adapter import adapt_collector_report
from app.application.job_imports.models import (
    AdaptedCollectorJob,
    AdaptedCollectorReport,
    ImportIssue,
    NormalizedCollectorReport,
    NormalizedJobInput,
)
from app.application.job_imports.normalizer import normalize_adapted_report

__all__ = [
    "AdaptedCollectorJob",
    "AdaptedCollectorReport",
    "ImportIssue",
    "NormalizedCollectorReport",
    "NormalizedJobInput",
    "adapt_collector_report",
    "normalize_adapted_report",
]
