"""Stable HTTP error mapping for application and request-boundary failures."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.schemas import ApiError, ApiErrorResponse
from app.application.career_context import (
    ContextVersionConflictError,
    InvalidCareerContextError,
    ProfileNotFoundError,
    SearchIntentNotFoundError,
)
from app.application.eligibility import EligibilityInputsNotReadyError
from app.application.evidence_retrieval import EvidenceRetrievalInputsNotReadyError
from app.application.create_target_cohort import TargetCohortSelectionError
from app.application.match_report import MatchReportPersistenceNotReadyError
from app.application.user_feedback import (
    FeedbackMatchReportMismatchError,
    FeedbackMatchReportNotFoundError,
    FeedbackMatchReportStaleError,
    UserFeedbackPersistenceNotReadyError,
)
from app.application.semantic_match.errors import (
    InvalidSemanticMatcherOutputError,
    SemanticMatcherFailedError,
    SemanticMatcherUnavailableError,
    SemanticMatchInputsNotReadyError,
)
from app.application.job_import_queries import JobImportNotFoundError
from app.application.job_imports.errors import (
    ImportIdentityConflictError,
    InvalidCollectorReportError,
    UnsupportedCollectorVersionError,
)
from app.application.job_queries import JobNotFoundError
from app.application.job_requirements import (
    InvalidRequirementExtractorOutputError,
    JobDescriptionNotExtractableError,
    JobRequirementExtractionNotFoundError,
    RequirementExtractorFailedError,
    RequirementExtractorUnavailableError,
)
from app.application.profile_evals import (
    AcceptedProfileEvalBaselineNotFoundError,
    InvalidProfileEvalReviewError,
    ProfileEvalRunAlreadyReviewedError,
    ProfileEvalRunNotFoundError,
)
from app.application.requirement_acceptance.errors import (
    InvalidRequirementAcceptanceCanaryReviewError,
    RequirementAcceptanceCanaryGateError,
    RequirementAcceptanceCanaryReviewAlreadyExistsError,
    RequirementAcceptanceRunNotFoundError,
)
from app.application.requirement_evals import (
    AcceptedRequirementEvalBaselineNotFoundError,
    InvalidRequirementEvalReviewError,
    RequirementEvalRunAlreadyReviewedError,
    RequirementEvalRunNotFoundError,
)
from app.application.requirement_reviews import (
    AcceptedRequirementReviewBaselineNotFoundError,
    InvalidRequirementCaseReviewError,
    InvalidRequirementReviewBatchError,
    InvalidRequirementReviewBatchFinalDecisionError,
    RequirementReviewBatchFinalDecisionAlreadyExistsError,
    RequirementReviewBatchNotFoundError,
    RequirementReviewCaseAlreadyReviewedError,
    RequirementReviewCaseNotFoundError,
)
from app.application.profile_extraction import (
    InvalidProfileExtractorOutputError,
    InvalidResumeTextError,
    ProfileExtractorFailedError,
    ProfileExtractorUnavailableError,
)
from app.application.resume_documents import (
    InvalidResumeDocumentError,
    ResumeDocumentTooLargeError,
    ResumeTextNotExtractableError,
    UnsupportedResumeDocumentError,
)

logger = logging.getLogger(__name__)


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    body = ApiErrorResponse(error=ApiError(code=code, message=message))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(by_alias=True),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register protocol-level mappings without leaking HTTP into Application."""

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "request_validation_error",
            "Request body or parameters are invalid.",
        )

    @app.exception_handler(EligibilityInputsNotReadyError)
    async def handle_eligibility_inputs_not_ready(
        _request: Request,
        error: EligibilityInputsNotReadyError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "eligibility_inputs_not_ready",
            str(error),
        )

    @app.exception_handler(EvidenceRetrievalInputsNotReadyError)
    async def handle_evidence_retrieval_inputs_not_ready(
        _request: Request,
        error: EvidenceRetrievalInputsNotReadyError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "evidence_retrieval_inputs_not_ready",
            str(error),
        )

    @app.exception_handler(SemanticMatchInputsNotReadyError)
    async def handle_semantic_match_inputs_not_ready(
        _request: Request,
        error: SemanticMatchInputsNotReadyError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "semantic_match_inputs_not_ready",
            str(error),
        )

    @app.exception_handler(MatchReportPersistenceNotReadyError)
    async def handle_match_report_persistence_not_ready(
        _request: Request,
        error: MatchReportPersistenceNotReadyError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "match_report_persistence_not_ready",
            str(error),
        )

    @app.exception_handler(TargetCohortSelectionError)
    async def handle_target_cohort_selection_error(
        _request: Request,
        error: TargetCohortSelectionError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "target_cohort_selection_invalid",
            str(error),
        )

    @app.exception_handler(UserFeedbackPersistenceNotReadyError)
    async def handle_user_feedback_persistence_not_ready(
        _request: Request,
        error: UserFeedbackPersistenceNotReadyError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "user_feedback_persistence_not_ready",
            str(error),
        )

    @app.exception_handler(FeedbackMatchReportNotFoundError)
    async def handle_feedback_match_report_not_found(
        _request: Request,
        error: FeedbackMatchReportNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "feedback_match_report_not_found",
            str(error),
        )

    @app.exception_handler(FeedbackMatchReportMismatchError)
    async def handle_feedback_match_report_mismatch(
        _request: Request,
        error: FeedbackMatchReportMismatchError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "feedback_match_report_mismatch",
            str(error),
        )

    @app.exception_handler(FeedbackMatchReportStaleError)
    async def handle_feedback_match_report_stale(
        _request: Request,
        error: FeedbackMatchReportStaleError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "feedback_match_report_stale",
            str(error),
        )

    @app.exception_handler(SemanticMatcherUnavailableError)
    async def handle_semantic_matcher_unavailable(
        _request: Request,
        error: SemanticMatcherUnavailableError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "semantic_matcher_unavailable",
            str(error),
        )

    @app.exception_handler(SemanticMatcherFailedError)
    async def handle_semantic_matcher_failed(
        _request: Request,
        error: SemanticMatcherFailedError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "semantic_matcher_failed",
            str(error),
        )

    @app.exception_handler(InvalidSemanticMatcherOutputError)
    async def handle_invalid_semantic_matcher_output(
        _request: Request,
        error: InvalidSemanticMatcherOutputError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "invalid_semantic_matcher_output",
            str(error),
        )

    @app.exception_handler(ProfileNotFoundError)
    async def handle_profile_not_found(
        _request: Request,
        error: ProfileNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "profile_not_found",
            str(error),
        )

    @app.exception_handler(SearchIntentNotFoundError)
    async def handle_search_intent_not_found(
        _request: Request,
        error: SearchIntentNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "search_intent_not_found",
            str(error),
        )

    @app.exception_handler(ContextVersionConflictError)
    async def handle_context_version_conflict(
        _request: Request,
        error: ContextVersionConflictError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "context_version_conflict",
            str(error),
        )

    @app.exception_handler(InvalidCareerContextError)
    async def handle_invalid_career_context(
        _request: Request,
        error: InvalidCareerContextError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_career_context",
            str(error),
        )

    @app.exception_handler(InvalidCollectorReportError)
    async def handle_invalid_report(
        _request: Request,
        error: InvalidCollectorReportError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_collector_report",
            str(error),
        )

    @app.exception_handler(UnsupportedCollectorVersionError)
    async def handle_unsupported_version(
        _request: Request,
        error: UnsupportedCollectorVersionError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "unsupported_collector_version",
            str(error),
        )

    @app.exception_handler(JobImportNotFoundError)
    async def handle_job_import_not_found(
        _request: Request,
        error: JobImportNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "job_import_not_found",
            str(error),
        )

    @app.exception_handler(JobNotFoundError)
    async def handle_job_not_found(
        _request: Request,
        error: JobNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "job_not_found",
            str(error),
        )

    @app.exception_handler(JobRequirementExtractionNotFoundError)
    async def handle_job_requirement_extraction_not_found(
        _request: Request,
        error: JobRequirementExtractionNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "job_requirement_extraction_not_found",
            str(error),
        )

    @app.exception_handler(JobDescriptionNotExtractableError)
    async def handle_job_description_not_extractable(
        _request: Request,
        error: JobDescriptionNotExtractableError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "job_description_not_extractable",
            str(error),
        )

    @app.exception_handler(RequirementExtractorUnavailableError)
    async def handle_requirement_extractor_unavailable(
        _request: Request,
        error: RequirementExtractorUnavailableError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "requirement_extractor_unavailable",
            str(error),
        )

    @app.exception_handler(RequirementExtractorFailedError)
    async def handle_requirement_extractor_failed(
        _request: Request,
        error: RequirementExtractorFailedError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "requirement_extractor_failed",
            str(error),
        )

    @app.exception_handler(InvalidRequirementExtractorOutputError)
    async def handle_invalid_requirement_extractor_output(
        _request: Request,
        error: InvalidRequirementExtractorOutputError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "invalid_requirement_extractor_output",
            str(error),
        )

    @app.exception_handler(ImportIdentityConflictError)
    async def handle_identity_conflict(
        _request: Request,
        error: ImportIdentityConflictError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "import_identity_conflict",
            str(error),
        )

    @app.exception_handler(ResumeDocumentTooLargeError)
    async def handle_resume_document_too_large(
        _request: Request,
        error: ResumeDocumentTooLargeError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "resume_document_too_large",
            str(error),
        )

    @app.exception_handler(UnsupportedResumeDocumentError)
    async def handle_unsupported_resume_document(
        _request: Request,
        error: UnsupportedResumeDocumentError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "unsupported_resume_document",
            str(error),
        )

    @app.exception_handler(InvalidResumeDocumentError)
    async def handle_invalid_resume_document(
        _request: Request,
        error: InvalidResumeDocumentError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_resume_document",
            str(error),
        )

    @app.exception_handler(ResumeTextNotExtractableError)
    async def handle_resume_text_not_extractable(
        _request: Request,
        error: ResumeTextNotExtractableError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "resume_text_not_extractable",
            str(error),
        )

    @app.exception_handler(ProfileEvalRunNotFoundError)
    async def handle_profile_eval_run_not_found(
        _request: Request,
        error: ProfileEvalRunNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "profile_eval_run_not_found",
            str(error),
        )

    @app.exception_handler(AcceptedProfileEvalBaselineNotFoundError)
    async def handle_accepted_profile_eval_baseline_not_found(
        _request: Request,
        error: AcceptedProfileEvalBaselineNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "accepted_profile_eval_baseline_not_found",
            str(error),
        )

    @app.exception_handler(ProfileEvalRunAlreadyReviewedError)
    async def handle_profile_eval_run_already_reviewed(
        _request: Request,
        error: ProfileEvalRunAlreadyReviewedError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "profile_eval_run_already_reviewed",
            str(error),
        )

    @app.exception_handler(InvalidProfileEvalReviewError)
    async def handle_invalid_profile_eval_review(
        _request: Request,
        error: InvalidProfileEvalReviewError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_profile_eval_review",
            str(error),
        )

    @app.exception_handler(RequirementEvalRunNotFoundError)
    async def handle_requirement_eval_run_not_found(
        _request: Request,
        error: RequirementEvalRunNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "requirement_eval_run_not_found",
            str(error),
        )

    @app.exception_handler(AcceptedRequirementEvalBaselineNotFoundError)
    async def handle_accepted_requirement_eval_baseline_not_found(
        _request: Request,
        error: AcceptedRequirementEvalBaselineNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "accepted_requirement_eval_baseline_not_found",
            str(error),
        )

    @app.exception_handler(RequirementEvalRunAlreadyReviewedError)
    async def handle_requirement_eval_run_already_reviewed(
        _request: Request,
        error: RequirementEvalRunAlreadyReviewedError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "requirement_eval_run_already_reviewed",
            str(error),
        )

    @app.exception_handler(InvalidRequirementEvalReviewError)
    async def handle_invalid_requirement_eval_review(
        _request: Request,
        error: InvalidRequirementEvalReviewError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_requirement_eval_review",
            str(error),
        )

    @app.exception_handler(RequirementAcceptanceRunNotFoundError)
    async def handle_requirement_acceptance_run_not_found(
        _request: Request,
        error: RequirementAcceptanceRunNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "requirement_acceptance_run_not_found",
            str(error),
        )

    @app.exception_handler(RequirementAcceptanceCanaryReviewAlreadyExistsError)
    async def handle_requirement_acceptance_canary_review_exists(
        _request: Request,
        error: RequirementAcceptanceCanaryReviewAlreadyExistsError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "requirement_acceptance_canary_review_already_exists",
            str(error),
        )

    @app.exception_handler(RequirementAcceptanceCanaryGateError)
    async def handle_requirement_acceptance_canary_gate(
        _request: Request,
        error: RequirementAcceptanceCanaryGateError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "requirement_acceptance_canary_gate_blocked",
            str(error),
        )

    @app.exception_handler(InvalidRequirementAcceptanceCanaryReviewError)
    async def handle_invalid_requirement_acceptance_canary_review(
        _request: Request,
        error: InvalidRequirementAcceptanceCanaryReviewError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_requirement_acceptance_canary_review",
            str(error),
        )

    @app.exception_handler(RequirementReviewBatchNotFoundError)
    async def handle_requirement_review_batch_not_found(
        _request: Request,
        error: RequirementReviewBatchNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "requirement_review_batch_not_found",
            str(error),
        )

    @app.exception_handler(RequirementReviewCaseNotFoundError)
    async def handle_requirement_review_case_not_found(
        _request: Request,
        error: RequirementReviewCaseNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "requirement_review_case_not_found",
            str(error),
        )

    @app.exception_handler(RequirementReviewCaseAlreadyReviewedError)
    async def handle_requirement_review_case_already_reviewed(
        _request: Request,
        error: RequirementReviewCaseAlreadyReviewedError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "requirement_review_case_already_reviewed",
            str(error),
        )

    @app.exception_handler(InvalidRequirementReviewBatchError)
    async def handle_invalid_requirement_review_batch(
        _request: Request,
        error: InvalidRequirementReviewBatchError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_requirement_review_batch",
            str(error),
        )

    @app.exception_handler(InvalidRequirementCaseReviewError)
    async def handle_invalid_requirement_case_review(
        _request: Request,
        error: InvalidRequirementCaseReviewError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_requirement_case_review",
            str(error),
        )

    @app.exception_handler(InvalidRequirementReviewBatchFinalDecisionError)
    async def handle_invalid_requirement_review_batch_final_decision(
        _request: Request,
        error: InvalidRequirementReviewBatchFinalDecisionError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_requirement_review_batch_final_decision",
            str(error),
        )

    @app.exception_handler(RequirementReviewBatchFinalDecisionAlreadyExistsError)
    async def handle_requirement_review_batch_final_decision_exists(
        _request: Request,
        error: RequirementReviewBatchFinalDecisionAlreadyExistsError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "requirement_review_batch_final_decision_already_exists",
            str(error),
        )

    @app.exception_handler(AcceptedRequirementReviewBaselineNotFoundError)
    async def handle_accepted_requirement_review_baseline_not_found(
        _request: Request,
        error: AcceptedRequirementReviewBaselineNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "accepted_requirement_review_baseline_not_found",
            str(error),
        )

    @app.exception_handler(InvalidResumeTextError)
    async def handle_invalid_resume_text(
        _request: Request,
        error: InvalidResumeTextError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_resume_text",
            str(error),
        )

    @app.exception_handler(ProfileExtractorUnavailableError)
    async def handle_profile_extractor_unavailable(
        _request: Request,
        error: ProfileExtractorUnavailableError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "profile_extractor_unavailable",
            str(error),
        )

    @app.exception_handler(ProfileExtractorFailedError)
    async def handle_profile_extractor_failed(
        _request: Request,
        error: ProfileExtractorFailedError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "profile_extractor_failed",
            str(error),
        )

    @app.exception_handler(InvalidProfileExtractorOutputError)
    async def handle_invalid_profile_extractor_output(
        _request: Request,
        error: InvalidProfileExtractorOutputError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "invalid_profile_extractor_output",
            str(error),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        logger.error(
            "Unhandled API error for %s %s",
            request.method,
            request.url.path,
            exc_info=(type(error), error, error.__traceback__),
        )
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_server_error",
            "An unexpected server error occurred.",
        )
