"""Eligibility execution errors."""


class EligibilityInputsNotReadyError(RuntimeError):
    """Raised when trusted Match inputs have not passed release gates."""
