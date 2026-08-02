"""Application use cases for listing and reading normalized jobs."""
from __future__ import annotations

from app.application.job_queries.errors import JobNotFoundError
from app.application.job_queries.models import JobDetail, JobListQuery, JobPage
from app.application.ports.job_query_repository import AbstractJobQueryRepository


class ListJobsUseCase:
    def __init__(self, repository: AbstractJobQueryRepository) -> None:
        self._repository = repository

    def execute(self, query: JobListQuery) -> JobPage:
        return self._repository.fetch_page(query)


class GetJobUseCase:
    def __init__(self, repository: AbstractJobQueryRepository) -> None:
        self._repository = repository

    def execute(self, job_id: str) -> JobDetail:
        job = self._repository.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        return job
