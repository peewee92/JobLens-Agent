"""Read-only explanation of current blocked MatchReports."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_match_blocker_summary_use_case
from app.api.v1.schemas.match_blockers import MatchBlockerSummaryResponse
from app.application.match_blocker_summary import BuildMatchBlockerSummaryUseCase

router = APIRouter(prefix="/match-blockers")


@router.get("", response_model=MatchBlockerSummaryResponse)
def get_match_blocker_summary(
    job_ids: Annotated[list[str], Query(alias="jobId", min_length=1)],
    use_case: Annotated[
        BuildMatchBlockerSummaryUseCase,
        Depends(get_match_blocker_summary_use_case),
    ],
) -> MatchBlockerSummaryResponse:
    summary = use_case.execute(tuple(job_ids))
    return MatchBlockerSummaryResponse.from_summary(summary)
