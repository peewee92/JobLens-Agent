"""Stable application errors for Job Requirement extraction."""
from __future__ import annotations


class JobDescriptionNotExtractableError(ValueError):
    """Persisted Job description is missing or outside supported boundaries."""


class JobRequirementExtractionExecutionError(RuntimeError):
    """Base error for traced Requirement Extractor attempts."""

    def __init__(self, message: str, *, run_id: str | None = None) -> None:
        super().__init__(message)
        self.run_id = run_id


class RequirementExtractorUnavailableError(JobRequirementExtractionExecutionError):
    """No configured Requirement Extractor can serve the request."""

    def __init__(
        self,
        message: str,
        *,
        run_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, run_id=run_id)
        self.status_code = status_code


class RequirementExtractorFailedError(JobRequirementExtractionExecutionError):
    """The provider failed before producing usable structured output."""


class InvalidRequirementExtractorOutputError(JobRequirementExtractionExecutionError):
    """Provider output violated deterministic Requirement rules."""


class JobRequirementExtractionNotFoundError(LookupError):
    """No latest or requested historical Requirement Extraction exists."""
