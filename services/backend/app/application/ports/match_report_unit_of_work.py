"""Transaction boundary for MatchReport persistence."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.ports.match_report_repository import AbstractMatchReportRepository


class AbstractMatchReportUnitOfWork(ABC):
    reports: AbstractMatchReportRepository

    @abstractmethod
    def __enter__(self) -> "AbstractMatchReportUnitOfWork":
        raise NotImplementedError

    @abstractmethod
    def __exit__(self, exc_type, exc, traceback) -> None:
        raise NotImplementedError

    def ensure_job_availability(self, job_id: str, revision: int) -> None:
        """Check availability in the report transaction before writing."""
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError
