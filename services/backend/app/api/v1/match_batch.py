"""Bounded Phase 5 Batch Match execution endpoint."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_batch_match_execution_use_case
from app.api.v1.schemas.match_batch import (
    BatchMatchExecutionRequest,
    BatchMatchExecutionResponse,
)
from app.application.match_batch_execution import ExecuteBatchMatchUseCase

router = APIRouter(prefix="/match-batch")


@router.post("", response_model=BatchMatchExecutionResponse)
def execute_batch_match(
    request: BatchMatchExecutionRequest,
    use_case: Annotated[
        ExecuteBatchMatchUseCase,
        Depends(get_batch_match_execution_use_case),
    ],
) -> BatchMatchExecutionResponse:
    result = use_case.execute(
        tuple(request.job_ids),
        max_ready_jobs=request.max_ready_jobs,
    )
    return BatchMatchExecutionResponse.from_result(result)
