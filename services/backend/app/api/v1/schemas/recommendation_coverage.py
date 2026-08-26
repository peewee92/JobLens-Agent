"""HTTP contract for read-only recommendation coverage planning."""
from __future__ import annotations

from app.api.v1.schemas.common import CamelCaseModel
from app.application.recommendation_coverage import RecommendationCoverage


class RecommendationCoverageCandidateResponse(CamelCaseModel):
    job_id: str
    title: str
    company: str
    area: str | None
    salary_min_k: float | None
    salary_max_k: float | None
    status: str
    blocker_codes: list[str]
    intent_signals: list[str]


class RecommendationCoverageResponse(CamelCaseModel):
    total_job_count: int
    considered_job_count: int
    current_report_count: int
    match_ready_without_report_count: int
    requirement_analysis_needed_count: int
    profile_blocked_count: int
    other_blocked_count: int
    next_analysis_candidates: list[RecommendationCoverageCandidateResponse]
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_detail(cls, detail: RecommendationCoverage) -> "RecommendationCoverageResponse":
        return cls(
            total_job_count=detail.total_job_count,
            considered_job_count=detail.considered_job_count,
            current_report_count=detail.current_report_count,
            match_ready_without_report_count=detail.match_ready_without_report_count,
            requirement_analysis_needed_count=detail.requirement_analysis_needed_count,
            profile_blocked_count=detail.profile_blocked_count,
            other_blocked_count=detail.other_blocked_count,
            next_analysis_candidates=[
                RecommendationCoverageCandidateResponse(
                    job_id=item.job_id,
                    title=item.title,
                    company=item.company,
                    area=item.area,
                    salary_min_k=item.salary_min_k,
                    salary_max_k=item.salary_max_k,
                    status=item.status.value,
                    blocker_codes=list(item.blocker_codes),
                    intent_signals=list(item.intent_signals),
                )
                for item in detail.next_analysis_candidates
            ],
            db_writes=detail.db_writes,
            provider_calls=detail.provider_calls,
            trace_runs_created=detail.trace_runs_created,
        )
