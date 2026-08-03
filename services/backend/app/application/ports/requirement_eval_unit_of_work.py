"""Transaction boundary for Requirement Eval run persistence."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.ports.requirement_eval_repository import (
    AbstractRequirementEvalRepository,
)


class AbstractRequirementEvalUnitOfWork(ABC):
    eval_runs: AbstractRequirementEvalRepository

    @abstractmethod
    def __enter__(self) -> "AbstractRequirementEvalUnitOfWork":
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
