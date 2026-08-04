"""Persistence ports for controlled Requirement acceptance execution runs."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.application.requirement_acceptance.runs import (
    RequirementAcceptanceCanaryReviewDetail,
    RequirementAcceptanceCanaryReviewWrite,
    RequirementAcceptanceRunCaseUpdate,
    RequirementAcceptanceRunDetail,
    RequirementAcceptanceRunPage,
    RequirementAcceptanceRunWrite,
)


class AbstractRequirementAcceptanceRunRepository(ABC):
    @abstractmethod
    def add_run(self, run: RequirementAcceptanceRunWrite) -> None:
        raise NotImplementedError

    @abstractmethod
    def try_acquire_execution_lease(
        self,
        *,
        identity_key: str,
        lease_token: str,
        acquired_at: datetime,
        expires_at: datetime,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def renew_execution_lease(
        self,
        *,
        identity_key: str,
        lease_token: str,
        renewed_at: datetime,
        expires_at: datetime,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def release_execution_lease(
        self,
        *,
        identity_key: str,
        lease_token: str,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def update_last_import(
        self,
        *,
        run_id: str,
        import_id: str,
        dataset_generated_at: str | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_case(self, update: RequirementAcceptanceRunCaseUpdate) -> None:
        raise NotImplementedError

    @abstractmethod
    def attach_batch(self, *, run_id: str, batch_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_canary_review(
        self,
        review: RequirementAcceptanceCanaryReviewWrite,
    ) -> None:
        raise NotImplementedError


class AbstractRequirementAcceptanceRunQueryRepository(ABC):
    @abstractmethod
    def list_runs(self, *, limit: int, offset: int) -> RequirementAcceptanceRunPage:
        raise NotImplementedError

    @abstractmethod
    def get_by_identity(
        self,
        *,
        dataset_fingerprint: str,
        title: str,
        reviewer: str,
        provider: str,
        model: str,
        extractor_version: str,
        prompt_version: str,
    ) -> RequirementAcceptanceRunDetail | None:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: str) -> RequirementAcceptanceRunDetail | None:
        raise NotImplementedError

    @abstractmethod
    def get_canary_review(
        self,
        run_id: str,
    ) -> RequirementAcceptanceCanaryReviewDetail | None:
        raise NotImplementedError
