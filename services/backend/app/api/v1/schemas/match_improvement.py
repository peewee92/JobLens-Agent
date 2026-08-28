"""HTTP contract for the read-only Match improvement comparison."""
from __future__ import annotations

from app.api.v1.schemas.common import CamelCaseModel
from app.application.match_improvement import MatchImprovement


class MatchImprovementResponse(CamelCaseModel):
    job_id: str
    current_report_id: str
    previous_report_id: str | None
    previous_recommendation: str | None
    current_recommendation: str
    previous_missing_requirement_count: int | None
    current_missing_requirement_count: int
    resolved_requirement_ids: list[str]
    newly_missing_requirement_ids: list[str]
    comparable: bool
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_detail(cls, detail: MatchImprovement) -> "MatchImprovementResponse":
        return cls(
            job_id=detail.job_id,
            current_report_id=detail.current_report_id,
            previous_report_id=detail.previous_report_id,
            previous_recommendation=(
                detail.previous_recommendation.value
                if detail.previous_recommendation is not None
                else None
            ),
            current_recommendation=detail.current_recommendation.value,
            previous_missing_requirement_count=detail.previous_missing_requirement_count,
            current_missing_requirement_count=detail.current_missing_requirement_count,
            resolved_requirement_ids=list(detail.resolved_requirement_ids),
            newly_missing_requirement_ids=list(detail.newly_missing_requirement_ids),
            comparable=detail.comparable,
            db_writes=detail.db_writes,
            provider_calls=detail.provider_calls,
            trace_runs_created=detail.trace_runs_created,
        )
