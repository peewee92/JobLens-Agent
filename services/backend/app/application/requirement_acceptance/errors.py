"""Stable errors for Requirement acceptance preparation."""


class InvalidRequirementAcceptanceDatasetError(ValueError):
    """Raised before persistence when a Collector review dataset is not formal input."""


class RequirementAcceptanceImportError(RuntimeError):
    """Raised when an accepted dataset cannot map to exactly 20 persisted Jobs."""


class RequirementAcceptanceRunNotFoundError(LookupError):
    """Raised when a controlled Requirement acceptance run does not exist."""


class RequirementAcceptanceCanaryReviewAlreadyExistsError(RuntimeError):
    """Raised when an immutable Canary decision already exists for the Run."""


class InvalidRequirementAcceptanceCanaryReviewError(ValueError):
    """Raised when a Canary review violates the frozen decision rules."""


class RequirementAcceptanceCanaryGateError(RuntimeError):
    """Raised when live extraction attempts are blocked by the human Canary gate."""


class RequirementAcceptanceExecutionLeaseUnavailableError(RuntimeError):
    """Raised before side effects when the same acceptance identity is already running."""


class RequirementAcceptanceExecutionLeaseLostError(RuntimeError):
    """Raised when the current execution can no longer prove lease ownership."""
