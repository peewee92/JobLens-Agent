"""Read-only Growth Loop endpoint for comparing consecutive MatchReport snapshots."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_match_improvement_use_case
from app.api.v1.schemas.match_improvement import MatchImprovementResponse
from app.application.match_improvement import GetMatchImprovementUseCase

router = APIRouter(prefix="/match-improvement")


@router.get("", response_model=MatchImprovementResponse)
def get_match_improvement(
    job_id: Annotated[str, Query(alias="jobId", min_length=1)],
    current_report_id: Annotated[str, Query(alias="currentReportId", min_length=1)],
    use_case: Annotated[
        GetMatchImprovementUseCase,
        Depends(get_match_improvement_use_case),
    ],
) -> MatchImprovementResponse:
    try:
        detail = use_case.execute(
            job_id=job_id,
            current_report_id=current_report_id,
        )
    except ValueError as exc:
        if str(exc) == "current_match_report_not_found":
            raise HTTPException(status_code=404, detail="Current MatchReport was not found for this Job.") from exc
        raise
    return MatchImprovementResponse.from_detail(detail)
