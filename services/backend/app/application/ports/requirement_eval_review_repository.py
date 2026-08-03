"""Persistence port for immutable Requirement Eval human Reviews."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.requirement_evals.models import RequirementEvalReviewWrite


class AbstractRequirementEvalReviewRepository(ABC):
    @abstractmethod
    def add(self, review: RequirementEvalReviewWrite) -> None:
        raise NotImplementedError
