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
        provider_calls: int = 0,
    ) -> None:
        super().__init__(message, run_id=run_id)
        self.status_code = status_code
        self.provider_calls = provider_calls


class RequirementExtractorFailedError(JobRequirementExtractionExecutionError):
    """The provider failed before producing usable structured output."""

    def __init__(
        self,
        message: str,
        *,
        run_id: str | None = None,
        failure_stage: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        provider_finish_reason: str | None = None,
        output_chars: int | None = None,
        requested_max_completion_tokens: int | None = None,
        provider_calls: int = 0,
    ) -> None:
        super().__init__(message, run_id=run_id)
        self.failure_stage = failure_stage
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.provider_finish_reason = provider_finish_reason
        self.output_chars = output_chars
        self.requested_max_completion_tokens = requested_max_completion_tokens
        self.provider_calls = provider_calls


class InvalidRequirementExtractorOutputError(JobRequirementExtractionExecutionError):
    """Provider output violated deterministic Requirement rules."""


class JobRequirementExtractionNotFoundError(LookupError):
    """No latest or requested historical Requirement Extraction exists."""
