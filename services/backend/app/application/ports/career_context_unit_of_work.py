"""Transaction boundary for versioned career-context commands."""
from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType

from app.application.ports.career_context_repository import (
    AbstractCareerContextRepository,
)


class AbstractCareerContextUnitOfWork(ABC):
    context: AbstractCareerContextRepository

    @abstractmethod
    def __enter__(self) -> "AbstractCareerContextUnitOfWork": ...

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
