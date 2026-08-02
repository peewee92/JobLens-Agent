"""Collector import boundary, normalization and application use case."""

from app.application.job_imports.adapter import adapt_collector_report
from app.application.job_imports.models import (
    AdaptedCollectorJob,
    AdaptedCollectorReport,
    ImportIssue,
    NormalizedCollectorReport,
    NormalizedJobInput,
)
from app.application.job_imports.normalizer import normalize_adapted_report
from app.application.job_imports.use_case import (
    ImportErrorDetail,
    ImportJobsResult,
    ImportJobsUseCase,
)

__all__ = [
    "AdaptedCollectorJob",
    "AdaptedCollectorReport",
    "ImportErrorDetail",
    "ImportIssue",
    "ImportJobsResult",
    "ImportJobsUseCase",
    "NormalizedCollectorReport",
    "NormalizedJobInput",
    "adapt_collector_report",
    "normalize_adapted_report",
]
