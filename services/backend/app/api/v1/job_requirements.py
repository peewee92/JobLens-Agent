"""HTTP endpoints for Job Requirement Extraction Runs."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    get_extract_job_requirements_use_case,
    get_job_eligibility_use_case,
    get_job_evidence_retrieval_use_case,
    get_job_requirement_extraction_use_case,
    get_job_requirement_release_readiness_use_case,
    get_latest_job_requirements_use_case,
    get_match_input_readiness_use_case,
    get_match_report_use_case,
    get_semantic_match_use_case,
)
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.eligibility import JobEligibilityResponse
from app.api.v1.schemas.evidence_retrieval import JobEvidenceRetrievalResponse
from app.api.v1.schemas.job_requirements import (
    JobRequirementExtractionRequest,
    JobRequirementExtractionResponse,
    JobRequirementReleaseReadinessResponse,
)
from app.api.v1.schemas.match_inputs import MatchInputReadinessResponse
from app.api.v1.schemas.match_report import JobMatchReportResponse
from app.api.v1.schemas.semantic_match import JobSemanticMatchResponse
from app.application.eligibility import EvaluateJobEligibilityUseCase
from app.application.evidence_retrieval import RetrieveJobEvidenceUseCase
from app.application.job_requirements.release import (
    GetJobRequirementReleaseReadinessUseCase,
)
from app.application.job_requirements import RequirementLiveCostConfirmationRequiredError
from app.application.job_requirements.use_cases import (
    ExtractJobRequirementsUseCase,
    GetJobRequirementExtractionUseCase,
    GetLatestJobRequirementsUseCase,
)
from app.application.match_inputs.readiness import GetMatchInputReadinessUseCase
from app.application.match_report import BuildJobMatchReportUseCase
from app.application.semantic_match.use_case import RunJobSemanticMatchUseCase

router = APIRouter(prefix="/jobs")


@router.post(
    "/{job_id}/requirement-extractions",
    response_model=JobRequirementExtractionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ApiErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
    },
)
def extract_job_requirements(
    job_id: str,
    use_case: Annotated[
        ExtractJobRequirementsUseCase,
        Depends(get_extract_job_requirements_use_case),
    ],
    request: JobRequirementExtractionRequest | None = None,
) -> JobRequirementExtractionResponse:
    if use_case.requires_live_cost_confirmation and not bool(request and request.confirm_live_cost):
        raise RequirementLiveCostConfirmationRequiredError(
            "Live Requirement extraction requires explicit per-run cost confirmation"
        )
    return JobRequirementExtractionResponse.from_detail(use_case.execute(job_id))


@router.get(
    "/{job_id}/requirement-release-readiness",
    response_model=JobRequirementReleaseReadinessResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse}},
)
def get_job_requirement_release_readiness(
    job_id: str,
    use_case: Annotated[
        GetJobRequirementReleaseReadinessUseCase,
        Depends(get_job_requirement_release_readiness_use_case),
    ],
) -> JobRequirementReleaseReadinessResponse:
    return JobRequirementReleaseReadinessResponse.from_detail(
        use_case.execute(job_id)
    )


@router.get(
    "/{job_id}/match-input-readiness",
    response_model=MatchInputReadinessResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse}},
)
def get_match_input_readiness(
    job_id: str,
    use_case: Annotated[
        GetMatchInputReadinessUseCase,
        Depends(get_match_input_readiness_use_case),
    ],
) -> MatchInputReadinessResponse:
    return MatchInputReadinessResponse.from_detail(use_case.execute(job_id))


@router.get(
    "/{job_id}/eligibility",
    response_model=JobEligibilityResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
    },
)
def get_job_eligibility(
    job_id: str,
    use_case: Annotated[
        EvaluateJobEligibilityUseCase,
        Depends(get_job_eligibility_use_case),
    ],
) -> JobEligibilityResponse:
    return JobEligibilityResponse.from_detail(use_case.execute(job_id))


@router.get(
    "/{job_id}/evidence-candidates",
    response_model=JobEvidenceRetrievalResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
    },
)
def get_job_evidence_candidates(
    job_id: str,
    use_case: Annotated[
        RetrieveJobEvidenceUseCase,
        Depends(get_job_evidence_retrieval_use_case),
    ],
) -> JobEvidenceRetrievalResponse:
    return JobEvidenceRetrievalResponse.from_detail(use_case.execute(job_id))


@router.post(
    "/{job_id}/semantic-match",
    response_model=JobSemanticMatchResponse,
    responses={
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ApiErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
    },
)
def run_semantic_match(
    job_id: str,
    use_case: Annotated[
        RunJobSemanticMatchUseCase,
        Depends(get_semantic_match_use_case),
    ],
) -> JobSemanticMatchResponse:
    return JobSemanticMatchResponse.from_detail(use_case.execute(job_id))


@router.post(
    "/{job_id}/match-report",
    response_model=JobMatchReportResponse,
    responses={
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ApiErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
    },
)
def build_match_report(
    job_id: str,
    use_case: Annotated[
        BuildJobMatchReportUseCase,
        Depends(get_match_report_use_case),
    ],
) -> JobMatchReportResponse:
    return JobMatchReportResponse.from_detail(use_case.execute(job_id))


@router.get(
    "/{job_id}/requirements",
    response_model=JobRequirementExtractionResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse}},
)
def get_latest_job_requirements(
    job_id: str,
    use_case: Annotated[
        GetLatestJobRequirementsUseCase,
        Depends(get_latest_job_requirements_use_case),
    ],
) -> JobRequirementExtractionResponse:
    return JobRequirementExtractionResponse.from_detail(use_case.execute(job_id))


@router.get(
    "/{job_id}/requirement-extractions/{extraction_id}",
    response_model=JobRequirementExtractionResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse}},
)
def get_job_requirement_extraction(
    job_id: str,
    extraction_id: str,
    use_case: Annotated[
        GetJobRequirementExtractionUseCase,
        Depends(get_job_requirement_extraction_use_case),
    ],
) -> JobRequirementExtractionResponse:
    return JobRequirementExtractionResponse.from_detail(
        use_case.execute(job_id=job_id, extraction_id=extraction_id)
    )
