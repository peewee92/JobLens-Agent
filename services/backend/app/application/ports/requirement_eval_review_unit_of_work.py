"""Transaction boundary for Requirement Eval human Reviews."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.ports.requirement_eval_review_repository import (
    AbstractRequirementEvalReviewRepository,
)


class AbstractRequirementEvalReviewUnitOfWork(ABC):
    reviews: AbstractRequirementEvalReviewRepository

    @abstractmethod
    def __enter__(self) -> "AbstractRequirementEvalReviewUnitOfWork":
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
