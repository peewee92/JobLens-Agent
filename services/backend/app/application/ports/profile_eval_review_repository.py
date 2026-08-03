"""Write port for immutable Profile Eval review decisions."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.profile_evals.models import ProfileEvalReviewWrite


class AbstractProfileEvalReviewRepository(ABC):
    @abstractmethod
    def add(self, review: ProfileEvalReviewWrite) -> None:
        raise NotImplementedError
