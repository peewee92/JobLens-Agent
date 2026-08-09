"""Persistence ports for immutable MatchReport history."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.application.match_report.models import MatchReport, StoredMatchReport


class AbstractMatchReportRepository(ABC):
    """Write repository used inside an explicit Unit of Work."""

    @abstractmethod
    def add(self, report: "MatchReport") -> "StoredMatchReport":
        raise NotImplementedError


class AbstractMatchReportQueryRepository(ABC):
    """Read-only access to immutable MatchReport history."""

    @abstractmethod
    def get(self, report_id: str) -> "StoredMatchReport | None":
        raise NotImplementedError

    @abstractmethod
    def list_for_job(self, job_id: str) -> "tuple[StoredMatchReport, ...]":
        raise NotImplementedError

    @abstractmethod
    def list_latest_for_jobs(self, job_ids: tuple[str, ...]) -> "tuple[StoredMatchReport, ...]":
        """Return at most one newest snapshot per requested Job, preserving request order."""
        raise NotImplementedError
