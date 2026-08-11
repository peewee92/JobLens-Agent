"""Read-only Phase 7 Job Preparation aggregate endpoint."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_job_preparation_bundle_use_case
from app.api.v1.schemas.job_preparation import JobPreparationResponse
from app.application.job_preparation.bundle import BuildJobPreparationBundleUseCase

router = APIRouter(prefix="/job-preparation")


@router.get("/{job_id}", response_model=JobPreparationResponse)
def get_job_preparation(
    job_id: str,
    use_case: Annotated[
        BuildJobPreparationBundleUseCase,
        Depends(get_job_preparation_bundle_use_case),
    ],
) -> JobPreparationResponse:
    return JobPreparationResponse.from_result(use_case.execute(job_id))
