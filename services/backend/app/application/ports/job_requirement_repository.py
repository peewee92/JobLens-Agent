"""Persistence ports for immutable Job Requirement Extraction Runs."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.job_requirements import (
    JobRequirementExtractionDetail,
    JobRequirementExtractionWrite,
)


class AbstractJobRequirementRepository(ABC):
    @abstractmethod
    def add(self, extraction: JobRequirementExtractionWrite) -> None:
        raise NotImplementedError


class AbstractJobRequirementQueryRepository(ABC):
    @abstractmethod
    def get_latest(self, job_id: str) -> JobRequirementExtractionDetail | None:
        raise NotImplementedError

    @abstractmethod
    def get_extraction(
        self,
        *,
        job_id: str,
        extraction_id: str,
    ) -> JobRequirementExtractionDetail | None:
        raise NotImplementedError
