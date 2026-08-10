"""Phase 5 immutable UserFeedback write endpoint."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_create_user_feedback_use_case
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.user_feedback import CreateUserFeedbackRequest, UserFeedbackResponse
from app.application.user_feedback import CreateUserFeedbackUseCase

router = APIRouter(prefix="/user-feedback")


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
