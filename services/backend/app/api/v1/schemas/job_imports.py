"""HTTP response contracts for the Job Import API."""
from __future__ import annotations

from app.api.v1.schemas.common import CamelCaseModel
from app.application.job_imports import ImportJobsResult


class JobImportErrorItem(CamelCaseModel):
    index: int
    stage: str
    code: str
    message: str


class JobImportResponse(CamelCaseModel):
    import_id: str
    source_version: str
    received: int
    created: int
    updated: int
    skipped: int
    errors: list[JobImportErrorItem]

    @classmethod
    def from_result(cls, result: ImportJobsResult) -> "JobImportResponse":
        return cls(
            import_id=result.import_id,
            source_version=result.source_version,
            received=result.received,
            created=result.created,
            updated=result.updated,
            skipped=result.skipped,
            errors=[
                JobImportErrorItem(
                    index=error.index,
                    stage=error.stage,
                    code=error.code,
                    message=error.message,
                )
                for error in result.errors
            ],
        )


class ApiError(CamelCaseModel):
    code: str
    message: str


class ApiErrorResponse(CamelCaseModel):
    error: ApiError
