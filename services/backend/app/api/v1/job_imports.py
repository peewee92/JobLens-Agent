"""HTTP adapter for Collector job imports."""
from __future__ import annotations

from typing import Any, Annotated

from fastapi import APIRouter, Body, Depends, status

from app.api.deps import get_import_jobs_use_case, get_job_import_detail_use_case
from app.api.v1.schemas import (
    ApiErrorResponse,
    JobImportDetailResponse,
    JobImportResponse,
)
from app.application.job_import_queries.use_cases import GetJobImportDetailUseCase
from app.application.job_imports import ImportJobsUseCase

router = APIRouter(prefix="/job-imports")


@router.get(
    "/{import_id}",
    response_model=JobImportDetailResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ApiErrorResponse},
    },
)
def get_job_import(
    import_id: str,
    use_case: Annotated[
        GetJobImportDetailUseCase,
        Depends(get_job_import_detail_use_case),
    ],
) -> JobImportDetailResponse:
    """Return one completed import batch with ordered per-item audit results."""

    return JobImportDetailResponse.from_detail(use_case.execute(import_id))


@router.post(
    "",
    response_model=JobImportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ApiErrorResponse},
    },
)
def create_job_import(
    payload: Annotated[dict[str, Any], Body(...)],
    use_case: Annotated[ImportJobsUseCase, Depends(get_import_jobs_use_case)],
) -> JobImportResponse:
    """Create one audited import batch from a Collector report JSON object."""

    result = use_case.execute(payload)
    return JobImportResponse.from_result(result)
