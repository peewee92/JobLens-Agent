"""Capability port for extracting structured Job Requirements."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.job_requirements import JobRequirementExtractorResult


class AbstractJobRequirementExtractor(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError

    @property
    def max_provider_calls_per_execution(self) -> int:
        """Upper bound for real Provider HTTP calls made by one extraction."""
        return 0

    @abstractmethod
    def extract(self, description: str) -> JobRequirementExtractorResult:
        raise NotImplementedError
