"""Application errors for Job Import audit queries."""


class JobImportNotFoundError(LookupError):
    """The requested Job Import audit record does not exist."""
