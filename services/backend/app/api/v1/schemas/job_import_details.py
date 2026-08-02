"""HTTP response contract for one Job Import audit detail."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.api.v1.schemas.common import CamelCaseModel
from app.application.job_import_queries.models import JobImportDetail
from app.domain.jobs import ImportOutcome


class JobImportAuditError(CamelCaseModel):
    index: int
    stage: str
    code: str
    message: str


class JobImportCandidateSummaryResponse(CamelCaseModel):
    total: int
    kept: int
    rejected: int
    unknown: int


class JobImportAuditItem(CamelCaseModel):
    input_index: int
    outcome: ImportOutcome
    job_id: str | None
    job_source_id: str | None
    error_code: str | None
    error_message: str | None


class JobImportDetailResponse(CamelCaseModel):
    import_id: str
    source_version: str
    collector_version: str | None
    received: int
    created: int
    updated: int
    skipped: int
    errors: list[JobImportAuditError]
    search_intent_snapshot: dict[str, Any]
    source_snapshot: dict[str, Any]
    candidate_summary: JobImportCandidateSummaryResponse
    collected_at: datetime | None
    created_at: datetime
    items: list[JobImportAuditItem]

    @classmethod
    def from_detail(cls, detail: JobImportDetail) -> "JobImportDetailResponse":
        return cls(
            import_id=detail.import_id,
            source_version=detail.source_version,
            collector_version=detail.collector_version,
            received=detail.received,
            created=detail.created,
            updated=detail.updated,
            skipped=detail.skipped,
            errors=[
                JobImportAuditError(
                    index=error.index,
                    stage=error.stage,
                    code=error.code,
                    message=error.message,
                )
                for error in detail.errors
            ],
            search_intent_snapshot=detail.search_intent_snapshot,
            source_snapshot=detail.source_snapshot,
            candidate_summary=JobImportCandidateSummaryResponse(
                total=detail.candidate_summary.total,
                kept=detail.candidate_summary.kept,
                rejected=detail.candidate_summary.rejected,
                unknown=detail.candidate_summary.unknown,
            ),
            collected_at=detail.collected_at,
            created_at=detail.created_at,
            items=[
                JobImportAuditItem(
                    input_index=item.input_index,
                    outcome=item.outcome,
                    job_id=item.job_id,
                    job_source_id=item.job_source_id,
                    error_code=item.error_code,
                    error_message=item.error_message,
                )
                for item in detail.items
            ],
        )
