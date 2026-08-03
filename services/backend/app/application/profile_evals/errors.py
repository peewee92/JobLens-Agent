"""Stable errors for Profile Eval run queries and execution."""


class ProfileEvalRunNotFoundError(LookupError):
    """Requested Eval Run or baseline does not exist."""
