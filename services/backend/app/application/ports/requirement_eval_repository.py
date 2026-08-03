"""Persistence ports for Requirement Eval runs."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.requirement_evals.models import (
    AcceptedRequirementEvalBaseline,
    RequirementEvalReviewDetail,
    RequirementEvalRunDetail,
    RequirementEvalRunPage,
    RequirementEvalRunSummary,
    RequirementEvalRunWrite,
)


class AbstractRequirementEvalRepository(ABC):
    @abstractmethod
    def add(self, run: RequirementEvalRunWrite) -> None:
        raise NotImplementedError


class AbstractRequirementEvalQueryRepository(ABC):
    @abstractmethod
    def list_runs(self, *, limit: int, offset: int) -> RequirementEvalRunPage:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, eval_run_id: str) -> RequirementEvalRunDetail | None:
        raise NotImplementedError

    @abstractmethod
    def get_summary(self, eval_run_id: str) -> RequirementEvalRunSummary | None:
        raise NotImplementedError

    @abstractmethod
    def get_review(self, eval_run_id: str) -> RequirementEvalReviewDetail | None:
        raise NotImplementedError

    @abstractmethod
    def get_accepted_baseline(self) -> AcceptedRequirementEvalBaseline | None:
        raise NotImplementedError
