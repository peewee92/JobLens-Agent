"""Transaction boundary for immutable Profile Eval review decisions."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.ports.profile_eval_review_repository import (
    AbstractProfileEvalReviewRepository,
)


class AbstractProfileEvalReviewUnitOfWork(ABC):
    reviews: AbstractProfileEvalReviewRepository

    @abstractmethod
    def __enter__(self) -> "AbstractProfileEvalReviewUnitOfWork":
        raise NotImplementedError

    @abstractmethod
    def __exit__(self, exc_type, exc, traceback) -> None:
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError
