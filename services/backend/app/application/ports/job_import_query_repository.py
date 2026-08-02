"""Application-owned port for Job Import audit reads."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.job_import_queries.models import JobImportDetail


class AbstractJobImportQueryRepository(ABC):
    @abstractmethod
    def get_import(self, import_id: str) -> JobImportDetail | None:
        """Return one completed import audit detail without exposing ORM rows."""
