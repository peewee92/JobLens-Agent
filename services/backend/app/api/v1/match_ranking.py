"""Read-only Phase 5 Batch Match Ranking endpoint."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_batch_match_ranking_use_case
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.match_ranking import BatchMatchRankingResponse
from app.application.match_ranking import BatchRankMatchReportsUseCase

router = APIRouter(prefix="/match-ranking")


@router.get(
    "",
    response_model=BatchMatchRankingResponse,
    responses={409: {"model": ApiErrorResponse}},
)
def get_batch_match_ranking(
    job_ids: Annotated[list[str], Query(alias="jobId", min_length=1)],
    use_case: Annotated[
        BatchRankMatchReportsUseCase,
        Depends(get_batch_match_ranking_use_case),
    ],
    include_blocked: Annotated[bool, Query(alias="includeBlocked")] = False,
    top_n: Annotated[int | None, Query(alias="topN", ge=1, le=50)] = None,
) -> BatchMatchRankingResponse:
    details = use_case.execute(
        tuple(job_ids),
        include_blocked=include_blocked,
        top_n=top_n,
    )
    return BatchMatchRankingResponse.from_details(details)
