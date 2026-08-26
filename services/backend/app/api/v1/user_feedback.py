"""Phase 5 immutable UserFeedback write endpoint."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    get_create_user_feedback_use_case,
    get_list_latest_user_feedback_use_case,
    get_list_user_feedback_use_case,
    get_user_feedback_match_eval_query_use_case,
)
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.user_feedback import (
    CreateUserFeedbackRequest,
    LatestUserFeedbackResponse,
    UserFeedbackHistoryResponse,
    UserFeedbackMatchEvalResponse,
    UserFeedbackResponse,
)
from app.application.user_feedback import (
    CreateUserFeedbackUseCase,
    ListLatestUserFeedbackUseCase,
    ListUserFeedbackUseCase,
)
from app.application.user_feedback_eval import UserFeedbackMatchEvalQueryUseCase

router = APIRouter(prefix="/user-feedback")


@router.get(
    "/eval",
    response_model=UserFeedbackMatchEvalResponse,
    responses={status.HTTP_409_CONFLICT: {"model": ApiErrorResponse}},
)
def get_user_feedback_match_eval(
    use_case: Annotated[
        UserFeedbackMatchEvalQueryUseCase,
        Depends(get_user_feedback_match_eval_query_use_case),
    ],
    job_id: Annotated[str, Query(alias="jobId", min_length=1)],
) -> UserFeedbackMatchEvalResponse:
    result = use_case.execute(job_id=job_id)
    return UserFeedbackMatchEvalResponse.from_result(result)


@router.get(
    "/latest",
    response_model=LatestUserFeedbackResponse,
    responses={status.HTTP_409_CONFLICT: {"model": ApiErrorResponse}},
)
def list_latest_user_feedback(
    use_case: Annotated[
        ListLatestUserFeedbackUseCase,
        Depends(get_list_latest_user_feedback_use_case),
    ],
    match_report_ids: Annotated[list[str], Query(alias="matchReportId")],
) -> LatestUserFeedbackResponse:
    result = use_case.execute(match_report_ids=tuple(match_report_ids))
    return LatestUserFeedbackResponse.from_result(result)


@router.get(
    "",
    response_model=UserFeedbackHistoryResponse,
    responses={status.HTTP_409_CONFLICT: {"model": ApiErrorResponse}},
)
def list_user_feedback(
    use_case: Annotated[
        ListUserFeedbackUseCase,
        Depends(get_list_user_feedback_use_case),
    ],
    match_report_id: Annotated[str | None, Query(alias="matchReportId")] = None,
    job_id: Annotated[str | None, Query(alias="jobId")] = None,
) -> UserFeedbackHistoryResponse:
    if bool(match_report_id) == bool(job_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="exactly one of matchReportId or jobId is required",
        )
    result = use_case.execute(match_report_id=match_report_id, job_id=job_id)
    return UserFeedbackHistoryResponse.from_result(result)


@router.post(
    "",
    response_model=UserFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
    },
)
def create_user_feedback(
    request: CreateUserFeedbackRequest,
    use_case: Annotated[
        CreateUserFeedbackUseCase,
        Depends(get_create_user_feedback_use_case),
    ],
) -> UserFeedbackResponse:
    result = use_case.execute(
        match_report_id=request.match_report_id,
        job_id=request.job_id,
        decision=request.decision,
        reasons=tuple(request.reasons),
        note=request.note,
    )
    return UserFeedbackResponse.from_result(result)
