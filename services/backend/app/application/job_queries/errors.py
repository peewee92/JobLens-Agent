"""Expected application errors for Job Pool queries."""


class JobNotFoundError(LookupError):
    """The requested JobLens-owned job resource does not exist."""


class JobAvailabilityPersistenceError(RuntimeError):
    """The result of the user availability write cannot be confirmed."""
