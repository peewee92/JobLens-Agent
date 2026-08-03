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
from app.application.job_import_queries import JobImportNotFoundError
from app.application.job_imports.errors import (
    ImportIdentityConflictError,
    InvalidCollectorReportError,
    UnsupportedCollectorVersionError,
)
from app.application.job_queries import JobNotFoundError
from app.application.profile_extraction import (
    InvalidProfileExtractorOutputError,
    InvalidResumeTextError,
    ProfileExtractorFailedError,
    ProfileExtractorUnavailableError,
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
