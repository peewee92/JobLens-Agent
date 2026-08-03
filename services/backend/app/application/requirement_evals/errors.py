"""Stable application errors for Requirement Eval runs."""


class RequirementEvalRunNotFoundError(LookupError):
    """Raised when an Eval Run or requested baseline does not exist."""


class RequirementEvalRunAlreadyReviewedError(RuntimeError):
    """Raised when an immutable Review already exists for the Run."""


class InvalidRequirementEvalReviewError(ValueError):
    """Raised when a Review violates governance policy."""


class AcceptedRequirementEvalBaselineNotFoundError(LookupError):
    """Raised when no human-accepted live Requirement baseline exists."""
