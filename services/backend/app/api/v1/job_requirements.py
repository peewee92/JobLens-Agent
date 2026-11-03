"""HTTP endpoints for Job Requirement Extraction Runs."""
from __future__ import annotations

from typing import Annotated

from fastapi import Request
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from dataclasses import asdict
from app.application.job_requirements.confirmation import ConfirmJobRequirementsUseCase, RequirementConfirmationConflict
from app.api.deps import get_confirm_job_requirements_use_case
from app.api.v1.schemas.job_requirements import JobRequirementConfirmationRequest, JobRequirementConfirmationResponse

from app.api.deps import (
    get_extract_job_requirements_use_case,
    get_job_eligibility_use_case,
    get_job_evidence_retrieval_use_case,
    get_job_requirement_extraction_use_case,
    get_job_requirement_release_readiness_use_case,
    get_latest_job_requirements_use_case,
    get_match_input_readiness_use_case,
    get_match_report_use_case,
    get_match_report_history_use_case,
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
from app.api.v1.schemas.match_report import (
    JobMatchReportResponse, MatchReportHistoryResponse, MatchReportHistoryItemResponse,
)
from app.application.match_report_history import GetMatchReportHistoryUseCase
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


@router.post("/{job_id}/requirement-confirmations", response_model=JobRequirementConfirmationResponse)
def confirm_job_requirements(
    job_id: str, payload: JobRequirementConfirmationRequest,
    use_case: Annotated[ConfirmJobRequirementsUseCase, Depends(get_confirm_job_requirements_use_case)],
):
    if not payload.confirmed:
        return JSONResponse({"error": {"code": "requirement_confirmation_required", "message": "请先核对当前岗位原文与全部提取要求。"}}, status_code=422)
    try:
        record = use_case.execute(job_id=job_id, extraction_id=payload.extraction_id,
            input_hash=payload.input_hash, facts_digest=payload.facts_digest, action_id=payload.action_id)
        return JobRequirementConfirmationResponse(**asdict(record))
    except RequirementConfirmationConflict as exc:
        return JSONResponse({"error": {"code": str(exc), "message": "岗位要求或确认请求已变化，请刷新核对后再确认。"}}, status_code=409)


@router.post(
    "/{job_id}/requirement-extractions",
    response_model=JobRequirementExtractionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
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


@router.get("/{job_id}/match-reports", response_model=MatchReportHistoryResponse)
def get_match_report_history(
    job_id: str,
    use_case: Annotated[GetMatchReportHistoryUseCase, Depends(get_match_report_history_use_case)],
) -> MatchReportHistoryResponse:
    entries = use_case.execute(job_id)
    return MatchReportHistoryResponse(items=[
        MatchReportHistoryItemResponse(
            report_id=item.stored.id,
            created_at=item.stored.created_at,
            is_current=not item.stale_reasons,
            stale_reasons=list(item.stale_reasons),
            report=JobMatchReportResponse.from_detail(item.stored.report),
        ) for item in entries
    ], count=len(entries))


from app.api.deps import get_authorized_requirement_extraction
from app.api.v1.schemas.requirement_calls import RequirementCallCommand, RequirementCallPlan, RequirementCallRecord
from app.application.job_requirements.call_models import RequirementCallConflict


@router.get("/{job_id}/requirement-call-plan", response_model=RequirementCallPlan)
def requirement_call_plan(job_id: str, service=Depends(get_authorized_requirement_extraction)):
    return service.plan(job_id)[0]


@router.get("/{job_id}/requirement-calls/{action_id}", response_model=RequirementCallRecord)
def requirement_call_status(job_id: str, action_id: str, service=Depends(get_authorized_requirement_extraction)):
    record = service.journal.get(job_id, action_id)
    if record is None:
        return JSONResponse({"error": {"code": "requirement_call_not_found", "message": "未找到本次分析请求。"}}, status_code=404)
    return record


@router.post("/{job_id}/requirement-calls", response_model=RequirementCallRecord)
def start_requirement_call(job_id: str, command: RequirementCallCommand, request: Request, service=Depends(get_authorized_requirement_extraction)):
    request.state.requirement_action_id = command.action_id
    try:
        return service.execute(job_id, command)
    except RequirementCallConflict as exc:
        return JSONResponse({"error": {"code": str(exc), "message": "本次授权未执行，请刷新检查岗位、调用范围与上次请求状态。", "retryable": False, "repairAction": "review_extraction_plan", "correlationId": command.action_id}}, status_code=409)
