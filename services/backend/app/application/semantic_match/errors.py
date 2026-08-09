"""Semantic Match application errors."""
from __future__ import annotations


class SemanticMatcherUnavailableError(RuntimeError):
    def __init__(self, message: str, *, run_id: str | None = None) -> None:
        super().__init__(message)
        self.run_id = run_id


class SemanticMatcherFailedError(RuntimeError):
    def __init__(self, message: str, *, run_id: str | None = None) -> None:
        super().__init__(message)
        self.run_id = run_id


class InvalidSemanticMatcherOutputError(ValueError):
    def __init__(self, message: str, *, run_id: str | None = None) -> None:
        super().__init__(message)
        self.run_id = run_id


class SemanticMatchInputsNotReadyError(RuntimeError):
    pass
