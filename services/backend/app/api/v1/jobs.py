"""HTTP adapters for Job Pool list and detail queries."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_get_job_use_case, get_list_jobs_use_case
from app.api.v1.schemas import (
    ApiErrorResponse,
    JobDetailResponse,
    JobListResponse,
)
from app.application.job_queries import JobListQuery, JobSort
from app.application.job_queries.use_cases import GetJobUseCase, ListJobsUseCase
from app.domain.jobs import RemoteStatus

router = APIRouter(prefix="/jobs")


@router.get("", response_model=JobListResponse)
def list_jobs(
    use_case: Annotated[ListJobsUseCase, Depends(get_list_jobs_use_case)],
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    city: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    min_salary_k: Annotated[
        float | None,
        Query(alias="minSalaryK", ge=0),
    ] = None,
    remote_status: Annotated[
        RemoteStatus | None,
        Query(alias="remoteStatus"),
    ] = None,
    source: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[JobSort, Query()] = JobSort.LATEST,
) -> JobListResponse:
    """Return one stable, filtered page from the normalized Job Pool."""

    page = use_case.execute(
        JobListQuery(
            q=q,
            city=city,
            min_salary_k=min_salary_k,
            remote_status=remote_status,
            source=source,
            limit=limit,
            offset=offset,
            sort=sort,
        )
    )
    return JobListResponse.from_page(page)


@router.get(
    "/{job_id}",
    response_model=JobDetailResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ApiErrorResponse},
    },
)
def get_job(
    job_id: str,
    use_case: Annotated[GetJobUseCase, Depends(get_get_job_use_case)],
) -> JobDetailResponse:
    """Return one public Job detail without raw or internal identity fields."""

    return JobDetailResponse.from_detail(use_case.execute(job_id))
