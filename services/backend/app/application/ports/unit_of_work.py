"""Unit-of-Work port that defines the application transaction boundary."""
from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.application.ports.job_repository import AbstractJobRepository


class AbstractUnitOfWork(ABC):
    """One business transaction with repositories sharing one Session.

    The application explicitly calls ``commit()`` only after every operation in
    the use case succeeds. Exiting without commit or exiting through an
    exception must leave no partial database state behind.
    """

    jobs: AbstractJobRepository

    @abstractmethod
    def __enter__(self) -> Self:
        """Open the transaction scope and expose repositories."""

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Rollback unfinished work and release database resources."""

    @abstractmethod
    def commit(self) -> None:
        """Atomically make all changes in this unit of work durable."""

    @abstractmethod
    def rollback(self) -> None:
        """Discard all uncommitted changes in this unit of work."""
