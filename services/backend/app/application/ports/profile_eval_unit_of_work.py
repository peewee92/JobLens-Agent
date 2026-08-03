"""Transaction boundary for Profile Eval run persistence."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.ports.profile_eval_repository import AbstractProfileEvalRepository


class AbstractProfileEvalUnitOfWork(ABC):
    eval_runs: AbstractProfileEvalRepository

    @abstractmethod
    def __enter__(self) -> "AbstractProfileEvalUnitOfWork":
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
