"""Transaction boundary for trace persistence."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.ports.trace_repository import AbstractTraceRepository


class AbstractTraceUnitOfWork(ABC):
    traces: AbstractTraceRepository

    @abstractmethod
    def __enter__(self) -> "AbstractTraceUnitOfWork":
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
