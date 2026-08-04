"""Transaction boundary for Requirement manual review writes."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.ports.requirement_review_repository import (
    AbstractRequirementReviewRepository,
)


class AbstractRequirementReviewUnitOfWork(ABC):
    reviews: AbstractRequirementReviewRepository

    @abstractmethod
    def __enter__(self) -> "AbstractRequirementReviewUnitOfWork":
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
