"""HTTP contract for the read-only Match blocker summary."""
from __future__ import annotations

from app.api.v1.schemas.common import CamelCaseModel
from app.application.match_blocker_summary import MatchBlockerSummary


class MatchBlockerCategoryResponse(CamelCaseModel):
    requirement_type: str
    missing_requirement_count: int
    affected_job_count: int
    affected_job_ids: list[str]
    examples: list[str]


class MatchBlockerSummaryResponse(CamelCaseModel):
    analyzed_report_count: int
    blocked_report_count: int
    missing_requirement_count: int
    resolved_missing_requirement_count: int
    unresolved_missing_requirement_ids: list[str]
    categories: list[MatchBlockerCategoryResponse]
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_summary(cls, summary: MatchBlockerSummary) -> "MatchBlockerSummaryResponse":
        return cls(
            analyzed_report_count=summary.analyzed_report_count,
            blocked_report_count=summary.blocked_report_count,
            missing_requirement_count=summary.missing_requirement_count,
            resolved_missing_requirement_count=summary.resolved_missing_requirement_count,
            unresolved_missing_requirement_ids=list(summary.unresolved_missing_requirement_ids),
            categories=[
                MatchBlockerCategoryResponse(
                    requirement_type=item.requirement_type.value,
                    missing_requirement_count=item.missing_requirement_count,
                    affected_job_count=item.affected_job_count,
                    affected_job_ids=list(item.affected_job_ids),
                    examples=list(item.examples),
                )
                for item in summary.categories
            ],
            db_writes=summary.db_writes,
            provider_calls=summary.provider_calls,
            trace_runs_created=summary.trace_runs_created,
        )
