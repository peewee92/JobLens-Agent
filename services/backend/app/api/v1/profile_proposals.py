"""HTTP adapter for resume-to-Profile proposals."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import (
    get_profile_document_workflow,
    get_profile_extraction_workflow,
)
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.profile_extraction import (
    ProfileExtractionProposalResponse,
    ProfileExtractionRequest,
)
from app.application.resume_documents import (
    InvalidResumeDocumentError,
    MAX_RESUME_FILE_BYTES,
    ResumeDocumentInput,
    ResumeDocumentTooLargeError,
)
from app.workflows import (
    ProposeProfileFromDocumentWorkflow,
    ProposeProfileFromResumeWorkflow,
)

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


@router.post(
    "/file",
    response_model=ProfileExtractionProposalResponse,
    responses={
        status.HTTP_413_CONTENT_TOO_LARGE: {"model": ApiErrorResponse},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"model": ApiErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ApiErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ApiErrorResponse},
    },
)
async def propose_profile_from_file(
    workflow: Annotated[
        ProposeProfileFromDocumentWorkflow,
        Depends(get_profile_document_workflow),
    ],
    file: Annotated[UploadFile | None, File()] = None,
) -> ProfileExtractionProposalResponse:
    """Parse one bounded PDF/DOCX and return a reviewable proposal."""

    if file is None:
        raise InvalidResumeDocumentError("Request must contain a resume file.")

    chunks: list[bytes] = []
    size = 0
    try:
        while chunk := await file.read(64 * 1024):
            size += len(chunk)
            if size > MAX_RESUME_FILE_BYTES:
                raise ResumeDocumentTooLargeError(
                    f"Resume document exceeds {MAX_RESUME_FILE_BYTES} bytes."
                )
            chunks.append(chunk)
    finally:
        await file.close()

    proposal = workflow.execute(
        ResumeDocumentInput(
            filename=file.filename or "resume",
            content_type=file.content_type,
            content=b"".join(chunks),
        )
    )
    return ProfileExtractionProposalResponse.from_proposal(proposal)
