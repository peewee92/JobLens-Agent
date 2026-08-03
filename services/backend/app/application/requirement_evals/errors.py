"""Stable application errors for Requirement Eval runs."""


class RequirementEvalRunNotFoundError(LookupError):
    """Raised when an Eval Run or requested baseline does not exist."""
