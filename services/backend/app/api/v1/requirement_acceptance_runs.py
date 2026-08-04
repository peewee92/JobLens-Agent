"""Read-only HTTP endpoint for controlled Requirement acceptance runs."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_list_requirement_acceptance_runs_use_case,
    get_requirement_acceptance_readiness_dashboard_use_case,
    get_requirement_acceptance_run_use_case,
    get_review_requirement_acceptance_canary_use_case,
)
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.requirement_acceptance_runs import (
    RequirementAcceptanceCanaryReviewRequest,
    RequirementAcceptanceCanaryReviewResponse,
    RequirementAcceptanceReadinessResponse,
    RequirementAcceptanceRunDetailResponse,
    RequirementAcceptanceRunPageResponse,
)
from app.application.requirement_acceptance.readiness_dashboard import (
    GetRequirementAcceptanceReadinessDashboardUseCase,
)
from app.application.requirement_acceptance.run_use_cases import (
    GetRequirementAcceptanceRunUseCase,
    ListRequirementAcceptanceRunsUseCase,
    ReviewRequirementAcceptanceCanaryUseCase,
)

router = APIRouter(prefix="/requirement-acceptance-runs")


@router.get("", response_model=RequirementAcceptanceRunPageResponse)
def list_requirement_acceptance_runs(
    use_case: Annotated[
        ListRequirementAcceptanceRunsUseCase,
        Depends(get_list_requirement_acceptance_runs_use_case),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RequirementAcceptanceRunPageResponse:
    return RequirementAcceptanceRunPageResponse.from_page(
        use_case.execute(limit=limit, offset=offset)
    )


@router.get(
    "/readiness",
    response_model=RequirementAcceptanceReadinessResponse,
)
def get_requirement_acceptance_readiness(
    use_case: Annotated[
        GetRequirementAcceptanceReadinessDashboardUseCase,
        Depends(get_requirement_acceptance_readiness_dashboard_use_case),
    ],
    reviewer: Annotated[str, Query(max_length=120)] = "",
    title: Annotated[str | None, Query(max_length=200)] = None,
    max_new_extractions: Annotated[int, Query(ge=1, le=20)] = 1,
) -> RequirementAcceptanceReadinessResponse:
    return RequirementAcceptanceReadinessResponse.from_dashboard(
        use_case.execute(
            reviewer=reviewer,
            title=title,
            max_new_extractions=max_new_extractions,
        )
    )


@router.get(
    "/{run_id}",
    response_model=RequirementAcceptanceRunDetailResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse}},
)
def get_requirement_acceptance_run(
    run_id: str,
    use_case: Annotated[
        GetRequirementAcceptanceRunUseCase,
        Depends(get_requirement_acceptance_run_use_case),
    ],
) -> RequirementAcceptanceRunDetailResponse:
    return RequirementAcceptanceRunDetailResponse.from_detail(use_case.execute(run_id))


@router.post(
    "/{run_id}/canary-review",
    response_model=RequirementAcceptanceCanaryReviewResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse},
    },
)
def review_requirement_acceptance_canary(
    run_id: str,
    request: RequirementAcceptanceCanaryReviewRequest,
    use_case: Annotated[
        ReviewRequirementAcceptanceCanaryUseCase,
        Depends(get_review_requirement_acceptance_canary_use_case),
    ],
) -> RequirementAcceptanceCanaryReviewResponse:
    return RequirementAcceptanceCanaryReviewResponse.from_detail(
        use_case.execute(
            run_id=run_id,
            reviewer=request.reviewer,
            decision=request.decision,
            notes=request.notes,
        )
    )
