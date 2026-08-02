"""Application use case for reading one Job Import audit detail."""
from __future__ import annotations

from app.application.job_import_queries.errors import JobImportNotFoundError
from app.application.job_import_queries.models import JobImportDetail
from app.application.ports.job_import_query_repository import (
    AbstractJobImportQueryRepository,
)


class GetJobImportDetailUseCase:
    def __init__(self, repository: AbstractJobImportQueryRepository) -> None:
        self._repository = repository

    def execute(self, import_id: str) -> JobImportDetail:
        detail = self._repository.get_import(import_id)
        if detail is None:
            raise JobImportNotFoundError(f"Job import not found: {import_id}")
        return detail
