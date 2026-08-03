"""Read-only HTTP endpoints for persisted Requirement Eval runs."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_get_requirement_eval_run_use_case,
    get_list_requirement_eval_runs_use_case,
)
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.requirement_evals import (
    RequirementEvalRunDetailResponse,
    RequirementEvalRunPageResponse,
)
from app.application.requirement_evals.use_cases import (
    GetRequirementEvalRunUseCase,
    ListRequirementEvalRunsUseCase,
)

router = APIRouter(prefix="/requirement-evals")


@router.get("", response_model=RequirementEvalRunPageResponse)
def list_requirement_eval_runs(
    use_case: Annotated[
        ListRequirementEvalRunsUseCase,
        Depends(get_list_requirement_eval_runs_use_case),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RequirementEvalRunPageResponse:
    return RequirementEvalRunPageResponse.from_page(
        use_case.execute(limit=limit, offset=offset)
    )


@router.get(
    "/{eval_run_id}",
    response_model=RequirementEvalRunDetailResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse}},
)
def get_requirement_eval_run(
    eval_run_id: str,
    use_case: Annotated[
        GetRequirementEvalRunUseCase,
        Depends(get_get_requirement_eval_run_use_case),
    ],
) -> RequirementEvalRunDetailResponse:
    return RequirementEvalRunDetailResponse.from_detail(
        use_case.execute(eval_run_id)
    )
