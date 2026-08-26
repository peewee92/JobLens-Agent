"""Read-only coverage endpoint for the main recommendation loop."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_recommendation_coverage_use_case
from app.api.v1.schemas.recommendation_coverage import RecommendationCoverageResponse
from app.application.recommendation_coverage import BuildRecommendationCoverageUseCase

router = APIRouter(prefix="/recommendation-coverage")


@router.get("", response_model=RecommendationCoverageResponse)
def get_recommendation_coverage(
    use_case: Annotated[
        BuildRecommendationCoverageUseCase,
        Depends(get_recommendation_coverage_use_case),
    ],
) -> RecommendationCoverageResponse:
    return RecommendationCoverageResponse.from_detail(use_case.execute())
