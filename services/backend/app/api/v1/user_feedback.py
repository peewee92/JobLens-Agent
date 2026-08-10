"""Phase 5 immutable UserFeedback write endpoint."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_create_user_feedback_use_case, get_list_user_feedback_use_case
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.user_feedback import (
    CreateUserFeedbackRequest,
    UserFeedbackHistoryResponse,
    UserFeedbackResponse,
)
from app.application.user_feedback import CreateUserFeedbackUseCase, ListUserFeedbackUseCase

router = APIRouter(prefix="/user-feedback")


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
