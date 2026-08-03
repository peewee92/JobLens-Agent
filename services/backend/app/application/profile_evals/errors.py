"""Stable errors for Profile Eval run queries and execution."""


class ProfileEvalRunNotFoundError(LookupError):
    """Requested Eval Run or explicit baseline does not exist."""


class AcceptedProfileEvalBaselineNotFoundError(LookupError):
    """No human-accepted live Profile Eval baseline exists."""


class InvalidProfileEvalReviewError(ValueError):
    """Review request violates live-evaluation governance rules."""


class ProfileEvalRunAlreadyReviewedError(RuntimeError):
    """An immutable Review already exists for the Eval Run."""
