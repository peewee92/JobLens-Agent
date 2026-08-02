"""Errors raised at the Collector import boundary."""


class JobImportBoundaryError(ValueError):
    """Base class for deterministic import-boundary failures."""


class InvalidCollectorReportError(JobImportBoundaryError):
    """The report envelope cannot be parsed or is structurally invalid."""


class UnsupportedCollectorVersionError(JobImportBoundaryError):
    """No adapter is registered for the supplied Collector version."""


class JobNormalizationError(JobImportBoundaryError):
    """One adapted job cannot be converted into the internal normalized shape."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CanonicalIdentityError(JobImportBoundaryError):
    """A stable canonical identity cannot be generated for a job."""
