"""Collector import boundary, normalization and lazy use-case exports."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.application.job_imports.adapter import adapt_collector_report
from app.application.job_imports.models import (
    AdaptedCollectorJob,
    AdaptedCollectorReport,
    ImportIssue,
    NormalizedCollectorReport,
    NormalizedJobInput,
)
from app.application.job_imports.normalizer import normalize_adapted_report

if TYPE_CHECKING:
    from app.application.job_imports.use_case import (
        ImportErrorDetail,
        ImportJobsResult,
        ImportJobsUseCase,
    )

_LAZY_USE_CASE_EXPORTS = {
    "ImportErrorDetail",
    "ImportJobsResult",
    "ImportJobsUseCase",
}


def __getattr__(name: str) -> Any:
    """Load the use-case module only when a public caller asks for it.

    The Repository Port imports job-import models. Eagerly importing the use
    case from this package initializer creates a clean-process circular import
    through ``application.ports``. Lazy export keeps the convenient public API
    without coupling model registration to use-case construction.
    """

    if name in _LAZY_USE_CASE_EXPORTS:
        from app.application.job_imports import use_case

        return getattr(use_case, name)
    raise AttributeError(name)


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
