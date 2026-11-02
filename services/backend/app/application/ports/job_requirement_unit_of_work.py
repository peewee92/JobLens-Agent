"""Transaction boundary for Job Requirement Extraction persistence."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.ports.job_requirement_repository import (
    AbstractJobRequirementRepository,
)


class AbstractJobRequirementUnitOfWork(ABC):
    requirements: AbstractJobRequirementRepository

    @abstractmethod
    def __enter__(self) -> "AbstractJobRequirementUnitOfWork":
        raise NotImplementedError

    @abstractmethod
    def __exit__(self, exc_type, exc, traceback) -> None:
        raise NotImplementedError

    def ensure_job_availability(self, job_id: str, revision: int) -> None:
        """Check the availability revision in the extraction write transaction."""
        raise NotImplementedError

    def ensure_description_hash(self, job_id: str, input_hash: str) -> None:
        """Check the original description under the existing write lock."""
        raise NotImplementedError

    def ensure_latest_extraction(self, job_id: str, expected_id: str | None) -> None:
        """Check the starting extraction version under the existing write lock."""
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError
