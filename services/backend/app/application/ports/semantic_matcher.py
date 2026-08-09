"""Capability port for structured Semantic Match judgments."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.semantic_match.models import (
    SemanticMatcherResult,
    SemanticRequirementInput,
)


class AbstractSemanticMatcher(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def match(
        self,
        requirements: tuple[SemanticRequirementInput, ...],
    ) -> SemanticMatcherResult:
        raise NotImplementedError
