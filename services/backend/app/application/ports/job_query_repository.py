"""Application-owned query port for the Job Pool read path."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.job_queries.models import JobDetail, JobListQuery, JobPage


class AbstractJobQueryRepository(ABC):
    """Read normalized jobs without exposing ORM models or SQLAlchemy types."""

    @abstractmethod
    def fetch_page(self, query: JobListQuery) -> JobPage:
        """Return total and items using one consistent filter definition."""

    @abstractmethod
    def get_job(self, job_id: str) -> JobDetail | None:
        """Return one public Job detail read model, if it exists."""
