"""Bounded Requirement Analysis endpoint for recommendation coverage expansion."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_requirement_batch_execution_use_case
from app.api.v1.schemas.requirement_batch import (
    RequirementBatchExecutionRequest,
    RequirementBatchExecutionResponse,
)
from app.application.requirement_batch_execution import ExecuteRequirementBatchUseCase

router = APIRouter(prefix="/requirement-batch")


@router.post("", response_model=RequirementBatchExecutionResponse)
def execute_requirement_batch(
    request: RequirementBatchExecutionRequest,
    use_case: Annotated[
        ExecuteRequirementBatchUseCase,
        Depends(get_requirement_batch_execution_use_case),
    ],
) -> RequirementBatchExecutionResponse:
    return RequirementBatchExecutionResponse.from_result(
        use_case.execute(
            tuple(request.job_ids),
            max_ready_jobs=request.max_ready_jobs,
        )
    )
