"""Persistence ports for immutable UserFeedback history."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.user_feedback import StoredUserFeedback, UserFeedbackDraft


class AbstractUserFeedbackRepository(ABC):
    @abstractmethod
    def add(self, feedback: "UserFeedbackDraft") -> "StoredUserFeedback":
        raise NotImplementedError


class AbstractUserFeedbackQueryRepository(ABC):
    @abstractmethod
    def get(self, feedback_id: str) -> "StoredUserFeedback | None":
        raise NotImplementedError

    @abstractmethod
    def list_for_match_report(self, match_report_id: str) -> "tuple[StoredUserFeedback, ...]":
        raise NotImplementedError

    @abstractmethod
    def list_for_job(self, job_id: str) -> "tuple[StoredUserFeedback, ...]":
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> "tuple[StoredUserFeedback, ...]":
        raise NotImplementedError
