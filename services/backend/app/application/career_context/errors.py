"""Stable application errors for Profile and SearchIntent workflows."""


class ProfileNotFoundError(LookupError):
    def __init__(self) -> None:
        super().__init__("Career profile not found")


class SearchIntentNotFoundError(LookupError):
    def __init__(self) -> None:
        super().__init__("Search intent not found")


class ContextVersionConflictError(RuntimeError):
    def __init__(self, resource: str, expected: int, current: int) -> None:
        self.resource = resource
        self.expected = expected
        self.current = current
        super().__init__(
            f"{resource} version conflict: expected {expected}, current {current}"
        )


class InvalidCareerContextError(ValueError):
    """Raised when cross-field Profile/SearchIntent invariants fail."""
