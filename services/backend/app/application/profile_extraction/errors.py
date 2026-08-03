"""Stable application errors for Profile Extraction."""


class InvalidResumeTextError(ValueError):
    """Resume text is missing or outside the supported size boundary."""


class ProfileExtractorUnavailableError(RuntimeError):
    """No configured extractor can serve the request."""


class ProfileExtractorFailedError(RuntimeError):
    """The configured provider failed before producing usable output."""


class InvalidProfileExtractorOutputError(RuntimeError):
    """Provider output violated deterministic Profile proposal rules."""
