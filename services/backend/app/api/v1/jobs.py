"""HTTP adapters for Job Pool list and detail queries."""
from __future__ import annotations

from typing import Annotated
from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from pydantic import ConfigDict, Field, StrictBool
from app.api.v1.schemas.common import CamelCaseModel
from app.api.deps import get_set_job_availability_use_case
from app.application.job_queries.errors import JobAvailabilityPersistenceError

from app.api.deps import get_get_job_use_case, get_list_jobs_use_case, get_job_import_query_repository
from app.application.ports.job_import_query_repository import AbstractJobImportQueryRepository
from app.api.v1.schemas import (
    ApiErrorResponse,
    JobDetailResponse,
    JobListResponse,
)
from app.application.job_queries import JobListQuery, JobSort
from app.application.job_queries.use_cases import GetJobUseCase, ListJobsUseCase
from app.domain.jobs import RemoteStatus

router = APIRouter(prefix="/jobs")


class JobAvailabilityRequest(CamelCaseModel):
    model_config = ConfigDict(extra="forbid")
    user_marked_inactive: StrictBool
    expected_revision: int = Field(ge=0, strict=True)


class JobAvailabilityResponse(CamelCaseModel):
    job_id: str
    user_marked_inactive: bool
    availability_revision: int = Field(ge=0)


class JobDescriptionObservationResponse(CamelCaseModel):
    import_id: str
    input_index: int
    recorded_at: datetime
    description: str | None
    truncated: bool


class JobDescriptionObservationsResponse(CamelCaseModel):
    job_id: str
    items: list[JobDescriptionObservationResponse]
    has_more: bool


@router.get("/{job_id}/description-observations", response_model=JobDescriptionObservationsResponse)
def get_description_observations(
    job_id: str,
    jobs: Annotated[GetJobUseCase, Depends(get_get_job_use_case)],
    imports: Annotated[AbstractJobImportQueryRepository, Depends(get_job_import_query_repository)],
) -> JobDescriptionObservationsResponse:
    """Show at most ten recorded descriptions, never the raw collector payload."""
    jobs.execute(job_id)
    observations = imports.get_job_description_observations(job_id, 11)
    return JobDescriptionObservationsResponse(
        job_id=job_id, has_more=len(observations) > 10,
        items=[JobDescriptionObservationResponse.model_validate(item, from_attributes=True)
               for item in observations[:10]],
    )


@router.put("/{job_id}/user-availability", response_model=JobAvailabilityResponse)
def set_job_user_availability(job_id: str, request: JobAvailabilityRequest,
                              use_case=Depends(get_set_job_availability_use_case)):
    try:
        result = use_case.execute(job_id, inactive=request.user_marked_inactive,
                                expected_revision=request.expected_revision)
    except JobAvailabilityPersistenceError:
        return JSONResponse(status_code=503, content={"error": {"code": "job_availability_storage_unavailable", "message": "保存结果暂时无法确认，请刷新后核对。", "retryable": True, "repairAction": "reload_then_check", "correlationId": f"job-availability-{uuid4().hex}"}})
    if result is None:
        return JSONResponse(status_code=404, content={"error": {"code": "job_not_found", "message": "岗位不存在。"}})
    if result is False:
        return JSONResponse(status_code=409, content={"error": {"code": "job_availability_conflict", "message": "岗位标记已变化，请刷新后核对。", "retryable": False, "repairAction": "reload_then_check", "correlationId": f"job-availability-{uuid4().hex}"}})
    return result


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
