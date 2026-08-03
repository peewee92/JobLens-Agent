"""Read-only HTTP endpoints for persisted Profile Eval runs."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_get_profile_eval_run_use_case, get_list_profile_eval_runs_use_case
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.profile_evals import (
    ProfileEvalRunDetailResponse,
    ProfileEvalRunPageResponse,
)
from app.application.profile_evals.use_cases import (
    GetProfileEvalRunUseCase,
    ListProfileEvalRunsUseCase,
)

router = APIRouter(prefix="/profile-evals")


@router.get("", response_model=ProfileEvalRunPageResponse)
def list_profile_eval_runs(
    use_case: Annotated[
        ListProfileEvalRunsUseCase,
        Depends(get_list_profile_eval_runs_use_case),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProfileEvalRunPageResponse:
    return ProfileEvalRunPageResponse.from_page(
        use_case.execute(limit=limit, offset=offset)
    )


@router.get(
    "/{eval_run_id}",
    response_model=ProfileEvalRunDetailResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse}},
)
def get_profile_eval_run(
    eval_run_id: str,
    use_case: Annotated[
        GetProfileEvalRunUseCase,
        Depends(get_get_profile_eval_run_use_case),
    ],
) -> ProfileEvalRunDetailResponse:
    return ProfileEvalRunDetailResponse.from_detail(use_case.execute(eval_run_id))
