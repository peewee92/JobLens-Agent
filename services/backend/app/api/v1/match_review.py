"""Read-only readiness endpoint for the Phase 4 human Match review."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_match_review_readiness_use_case
from app.api.v1.schemas.match_review import MatchReviewReadinessResponse
from app.application.match_review import GetMatchReviewReadinessUseCase

router = APIRouter(prefix="/match-review")


@router.get("/readiness", response_model=MatchReviewReadinessResponse)
def get_match_review_readiness(
    use_case: Annotated[
        GetMatchReviewReadinessUseCase,
        Depends(get_match_review_readiness_use_case),
    ],
) -> MatchReviewReadinessResponse:
    return MatchReviewReadinessResponse.from_detail(use_case.execute())
