"""HTTP contract for read-only Batch Match Ranking."""
from __future__ import annotations

from datetime import datetime

from app.api.v1.schemas.common import CamelCaseModel
from app.application.match_report import StoredMatchReport


class RankedMatchReportItemResponse(CamelCaseModel):
    report_id: str
    created_at: datetime
    job_id: str
    profile_id: str
    profile_version: int
    extraction_id: str
    eligibility: str
    recommendation: str
    summary: str
    matched_requirement_ids: list[str]
    partial_requirement_ids: list[str]
    missing_requirement_ids: list[str]
    evidence_links: list[dict[str, object]]

    @classmethod
    def from_detail(cls, detail: StoredMatchReport) -> "RankedMatchReportItemResponse":
        report = detail.report
        return cls(
            report_id=detail.id,
            created_at=detail.created_at,
            job_id=report.job_id,
            profile_id=report.profile_id,
            profile_version=report.profile_version,
            extraction_id=report.extraction_id,
            eligibility=report.eligibility.value,
            recommendation=report.recommendation.value,
            summary=report.summary,
            matched_requirement_ids=list(report.matched_requirement_ids),
            partial_requirement_ids=list(report.partial_requirement_ids),
            missing_requirement_ids=list(report.missing_requirement_ids),
            evidence_links=[
                {
                    "requirementId": item.requirement_id,
                    "evidenceIds": list(item.evidence_ids),
                }
                for item in report.evidence_links
            ],
        )


class BatchMatchRankingResponse(CamelCaseModel):
    items: list[RankedMatchReportItemResponse]
    count: int
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0

    @classmethod
    def from_details(
        cls,
        details: tuple[StoredMatchReport, ...],
    ) -> "BatchMatchRankingResponse":
        return cls(
            items=[RankedMatchReportItemResponse.from_detail(item) for item in details],
            count=len(details),
        )
