"""Stable application errors for Requirement manual review batches."""


class RequirementReviewBatchNotFoundError(LookupError):
    """Raised when a manual review batch does not exist."""


class RequirementReviewCaseNotFoundError(LookupError):
    """Raised when a case does not belong to the requested batch."""


class InvalidRequirementReviewBatchError(ValueError):
    """Raised when batch creation violates snapshot/cohort rules."""


class InvalidRequirementCaseReviewError(ValueError):
    """Raised when an accepted/rejected case review is inconsistent."""


class RequirementReviewCaseAlreadyReviewedError(RuntimeError):
    """Raised when one immutable case judgment already exists."""


class InvalidRequirementReviewBatchFinalDecisionError(ValueError):
    """Raised when a batch cannot receive an official final quality decision."""


class RequirementReviewBatchFinalDecisionAlreadyExistsError(RuntimeError):
    """Raised when one immutable batch final decision already exists."""


class AcceptedRequirementReviewBaselineNotFoundError(LookupError):
    """Raised when no current human-accepted Requirement baseline exists."""
