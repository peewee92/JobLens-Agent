"""HTTP endpoints for Requirement manual quality review batches."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_accepted_requirement_review_baseline_use_case,
    get_create_requirement_review_batch_use_case,
    get_finalize_requirement_review_batch_use_case,
    get_get_requirement_review_batch_use_case,
    get_list_requirement_review_batches_use_case,
    get_list_requirement_review_candidates_use_case,
    get_review_requirement_batch_case_use_case,
)
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.requirement_reviews import (
    AcceptedRequirementReviewBaselineResponse,
    CreateRequirementReviewBatchRequest,
    RequirementReviewBatchFinalDecisionRequest,
    RequirementReviewBatchFinalDecisionResponse,
    RequirementReviewBatchDetailResponse,
    RequirementReviewBatchPageResponse,
    RequirementReviewCandidatePageResponse,
    RequirementReviewCaseReviewRequest,
    RequirementReviewCaseReviewResponse,
)
from app.application.requirement_reviews.use_cases import (
    CreateRequirementReviewBatchUseCase,
    FinalizeRequirementReviewBatchUseCase,
    GetAcceptedRequirementReviewBaselineUseCase,
    GetRequirementReviewBatchUseCase,
    ListRequirementReviewBatchesUseCase,
    ListRequirementReviewCandidatesUseCase,
    ReviewRequirementBatchCaseUseCase,
)

router = APIRouter(prefix="/requirement-review-batches")


@router.get(
    "/candidates",
    response_model=RequirementReviewCandidatePageResponse,
)
def list_requirement_review_candidates(
    use_case: Annotated[
        ListRequirementReviewCandidatesUseCase,
        Depends(get_list_requirement_review_candidates_use_case),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RequirementReviewCandidatePageResponse:
    return RequirementReviewCandidatePageResponse.from_page(
        use_case.execute(limit=limit, offset=offset)
    )


@router.post(
    "",
    response_model=RequirementReviewBatchDetailResponse,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse}},
)
def create_requirement_review_batch(
    request: CreateRequirementReviewBatchRequest,
    use_case: Annotated[
        CreateRequirementReviewBatchUseCase,
        Depends(get_create_requirement_review_batch_use_case),
    ],
) -> RequirementReviewBatchDetailResponse:
    return RequirementReviewBatchDetailResponse.from_detail(
        use_case.execute(
            title=request.title,
            reviewer=request.reviewer,
            extraction_ids=tuple(request.extraction_ids),
        )
    )


@router.get("", response_model=RequirementReviewBatchPageResponse)
def list_requirement_review_batches(
    use_case: Annotated[
        ListRequirementReviewBatchesUseCase,
        Depends(get_list_requirement_review_batches_use_case),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RequirementReviewBatchPageResponse:
    return RequirementReviewBatchPageResponse.from_page(
        use_case.execute(limit=limit, offset=offset)
    )


@router.get(
    "/accepted-baseline",
    response_model=AcceptedRequirementReviewBaselineResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse}},
)
def get_accepted_requirement_review_baseline(
    use_case: Annotated[
        GetAcceptedRequirementReviewBaselineUseCase,
        Depends(get_accepted_requirement_review_baseline_use_case),
    ],
) -> AcceptedRequirementReviewBaselineResponse:
    return AcceptedRequirementReviewBaselineResponse.from_baseline(use_case.execute())


@router.get(
    "/{batch_id}",
    response_model=RequirementReviewBatchDetailResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse}},
)
def get_requirement_review_batch(
    batch_id: str,
    use_case: Annotated[
        GetRequirementReviewBatchUseCase,
        Depends(get_get_requirement_review_batch_use_case),
    ],
) -> RequirementReviewBatchDetailResponse:
    return RequirementReviewBatchDetailResponse.from_detail(use_case.execute(batch_id))


@router.post(
    "/{batch_id}/final-decision",
    response_model=RequirementReviewBatchFinalDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse},
    },
)
def finalize_requirement_review_batch(
    batch_id: str,
    request: RequirementReviewBatchFinalDecisionRequest,
    use_case: Annotated[
        FinalizeRequirementReviewBatchUseCase,
        Depends(get_finalize_requirement_review_batch_use_case),
    ],
) -> RequirementReviewBatchFinalDecisionResponse:
    return RequirementReviewBatchFinalDecisionResponse.from_detail(
        use_case.execute(
            batch_id=batch_id,
            decision=request.decision,
            reviewer=request.reviewer,
            notes=request.notes,
        )
    )


@router.post(
    "/{batch_id}/cases/{case_id}/review",
    response_model=RequirementReviewCaseReviewResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse},
    },
)
def review_requirement_batch_case(
    batch_id: str,
    case_id: str,
    request: RequirementReviewCaseReviewRequest,
    use_case: Annotated[
        ReviewRequirementBatchCaseUseCase,
        Depends(get_review_requirement_batch_case_use_case),
    ],
) -> RequirementReviewCaseReviewResponse:
    return RequirementReviewCaseReviewResponse.from_detail(
        use_case.execute(
            batch_id=batch_id,
            case_id=case_id,
            decision=request.decision,
            issue_codes=tuple(request.issue_codes),
            notes=request.notes,
        )
    )
