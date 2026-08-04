"""Transaction boundary for Requirement acceptance execution-run writes."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.ports.requirement_acceptance_run_repository import (
    AbstractRequirementAcceptanceRunRepository,
)


class AbstractRequirementAcceptanceRunUnitOfWork(ABC):
    runs: AbstractRequirementAcceptanceRunRepository

    @abstractmethod
    def __enter__(self) -> "AbstractRequirementAcceptanceRunUnitOfWork":
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
