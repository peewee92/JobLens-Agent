"""Capability port for extracting structured Job Requirements."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.job_requirements import JobRequirementExtractorResult


class AbstractJobRequirementExtractor(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def extract(self, description: str) -> JobRequirementExtractorResult:
        raise NotImplementedError
