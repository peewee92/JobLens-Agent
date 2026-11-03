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

    def get_latest_id(self, job_id: str) -> str | None:
        """Read the current version identity without requiring its contents."""
        latest = self.get_latest(job_id)
        return latest.extraction_id if latest is not None else None

    @abstractmethod
    def get_extraction(
        self,
        *,
        job_id: str,
        extraction_id: str,
    ) -> JobRequirementExtractionDetail | None:
        raise NotImplementedError
