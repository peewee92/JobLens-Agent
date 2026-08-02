"""HTTP response contracts for the Job Import API."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.application.job_imports import ImportJobsResult


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class CamelCaseModel(BaseModel):
    """Serialize public API fields as camelCase while accepting Python names."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


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
