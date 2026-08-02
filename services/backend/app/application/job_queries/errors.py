"""Expected application errors for Job Pool queries."""


class JobNotFoundError(LookupError):
    """The requested JobLens-owned job resource does not exist."""
