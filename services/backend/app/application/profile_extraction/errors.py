"""Stable application errors for Profile Extraction."""
from __future__ import annotations


class InvalidResumeTextError(ValueError):
    """Resume text is missing or outside the supported size boundary."""


class ProfileExtractionExecutionError(RuntimeError):
    """Base error for traced extractor attempts."""

    def __init__(self, message: str, *, run_id: str | None = None) -> None:
        super().__init__(message)
        self.run_id = run_id


class ProfileExtractorUnavailableError(ProfileExtractionExecutionError):
    """No configured extractor can serve the request."""


class ProfileExtractorFailedError(ProfileExtractionExecutionError):
    """The configured provider failed before producing usable output."""


class InvalidProfileExtractorOutputError(ProfileExtractionExecutionError):
    """Provider output violated deterministic Profile proposal rules."""
