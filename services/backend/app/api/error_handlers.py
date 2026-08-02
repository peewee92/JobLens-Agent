"""Stable HTTP error mapping for application and request-boundary failures."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.schemas import ApiError, ApiErrorResponse
from app.application.job_imports.errors import (
    ImportIdentityConflictError,
    InvalidCollectorReportError,
    UnsupportedCollectorVersionError,
)
from app.application.job_queries import JobNotFoundError

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
