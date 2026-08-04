"""Persistence/query ports for Requirement manual review batches."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.requirement_reviews.models import (
    RequirementReviewBatchCaseLookup,
    RequirementReviewBatchDetail,
    RequirementReviewBatchPage,
    RequirementReviewBatchWrite,
    RequirementReviewCandidatePage,
    RequirementReviewCaseReviewDetail,
    RequirementReviewCaseReviewWrite,
    RequirementReviewExtractionSnapshot,
)


class AbstractRequirementReviewRepository(ABC):
    @abstractmethod
    def add_batch(self, batch: RequirementReviewBatchWrite) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_case_review(self, review: RequirementReviewCaseReviewWrite) -> None:
        raise NotImplementedError


class AbstractRequirementReviewQueryRepository(ABC):
    @abstractmethod
    def list_candidates(self, *, limit: int, offset: int) -> RequirementReviewCandidatePage:
        raise NotImplementedError

    @abstractmethod
    def get_extraction_snapshots(
        self,
        extraction_ids: tuple[str, ...],
    ) -> tuple[RequirementReviewExtractionSnapshot, ...]:
        raise NotImplementedError

    @abstractmethod
    def list_batches(self, *, limit: int, offset: int) -> RequirementReviewBatchPage:
        raise NotImplementedError

    @abstractmethod
    def get_batch(self, batch_id: str) -> RequirementReviewBatchDetail | None:
        raise NotImplementedError

    @abstractmethod
    def get_case(
        self,
        *,
        batch_id: str,
        case_id: str,
    ) -> RequirementReviewBatchCaseLookup | None:
        raise NotImplementedError

    @abstractmethod
    def get_case_review(self, case_id: str) -> RequirementReviewCaseReviewDetail | None:
        raise NotImplementedError
