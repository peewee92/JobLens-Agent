"""HTTP adapter for resume-to-Profile proposals."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_profile_extraction_workflow
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.profile_extraction import (
    ProfileExtractionProposalResponse,
    ProfileExtractionRequest,
)
from app.workflows import ProposeProfileFromResumeWorkflow

router = APIRouter(prefix="/profile-proposals")


@router.post(
    "",
    response_model=ProfileExtractionProposalResponse,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ApiErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ApiErrorResponse},
    },
)
def propose_profile(
    request: ProfileExtractionRequest,
    workflow: Annotated[
        ProposeProfileFromResumeWorkflow,
        Depends(get_profile_extraction_workflow),
    ],
) -> ProfileExtractionProposalResponse:
    """Return a reviewable proposal; never persist confirmed Profile facts."""

    proposal = workflow.execute(request.resume_text)
    return ProfileExtractionProposalResponse.from_proposal(proposal)
