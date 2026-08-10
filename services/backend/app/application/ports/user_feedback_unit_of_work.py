"""Unit of Work boundary for UserFeedback persistence."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.application.ports.user_feedback_repository import AbstractUserFeedbackRepository


class AbstractUserFeedbackUnitOfWork(ABC):
    feedback: "AbstractUserFeedbackRepository"

    @abstractmethod
    def __enter__(self) -> "AbstractUserFeedbackUnitOfWork":
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
