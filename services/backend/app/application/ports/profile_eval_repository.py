"""Persistence ports for Profile Eval runs."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.profile_evals.models import (
    ProfileEvalRunDetail,
    ProfileEvalRunPage,
    ProfileEvalRunSummary,
    ProfileEvalRunWrite,
)


class AbstractProfileEvalRepository(ABC):
    @abstractmethod
    def add(self, run: ProfileEvalRunWrite) -> None:
        raise NotImplementedError


class AbstractProfileEvalQueryRepository(ABC):
    @abstractmethod
    def list_runs(self, *, limit: int, offset: int) -> ProfileEvalRunPage:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, eval_run_id: str) -> ProfileEvalRunDetail | None:
        raise NotImplementedError

    @abstractmethod
    def get_summary(self, eval_run_id: str) -> ProfileEvalRunSummary | None:
        raise NotImplementedError
