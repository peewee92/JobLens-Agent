"""User-facing read model for explicit Target Cohort selection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.job_queries.models import JobListQuery
from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.application.ports.match_report_repository import AbstractMatchReportQueryRepository
from app.application.user_feedback import UserFeedbackPersistenceNotReadyError
from app.application.user_feedback_target_cohort import UserFeedbackTargetCohortSourceUseCase
from app.domain.user_feedback import FeedbackDecision, FeedbackReason


@dataclass(frozen=True, slots=True)
class TargetCohortCandidateItem:
    job_id: str
    title: str
    company: str
    area: str | None
    salary_min_k: float | None
    salary_max_k: float | None
    feedback_id: str | None = None
    decision: FeedbackDecision | None = None
    feedback_created_at: datetime | None = None
    reasons: tuple[FeedbackReason, ...] = ()
    note: str | None = None
    recommendation: str | None = None
    match_summary: str | None = None


@dataclass(frozen=True, slots=True)
class TargetCohortCandidatesResult:
    items: tuple[TargetCohortCandidateItem, ...]
    total_job_count: int
    total_feedback_records: int
    latest_job_feedback_count: int
    excluded_rejected_job_count: int
    feedback_overlay_available: bool
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class ListTargetCohortCandidatesUseCase:
    """List Job-pool candidates with optional latest-feedback context.

    The user selects Jobs directly. Feedback is only an explanatory overlay and is never
    required to create a manual TargetCohort. This keeps internal Feedback IDs out of the
    product task while preserving their provenance when they exist.
    """

    def __init__(
        self,
        *,
        source: UserFeedbackTargetCohortSourceUseCase,
        jobs: AbstractJobQueryRepository,
        reports: AbstractMatchReportQueryRepository,
    ) -> None:
        self._source = source
        self._jobs = jobs
        self._reports = reports

    def execute(self) -> TargetCohortCandidatesResult:
        page = self._jobs.fetch_page(JobListQuery(limit=100, offset=0))
        feedback_by_job = {}
        rejected_job_ids: set[str] = set()
        total_feedback_records = 0
        latest_job_feedback_count = 0
        feedback_overlay_available = True
        try:
            source_result = self._source.execute()
        except UserFeedbackPersistenceNotReadyError:
            feedback_overlay_available = False
        else:
            feedback_by_job = {item.job_id: item for item in source_result.candidates}
            rejected_job_ids = set(source_result.excluded_rejected_job_ids)
            total_feedback_records = source_result.total_feedback_records
            latest_job_feedback_count = source_result.latest_job_feedback_count

        items: list[TargetCohortCandidateItem] = []
        for job in page.items:
            feedback = feedback_by_job.get(job.id)
            decision = feedback.decision if feedback else None
            if feedback is None and job.id in rejected_job_ids:
                decision = FeedbackDecision.REJECTED

            report = self._reports.get(feedback.match_report_id) if feedback else None
            items.append(
                TargetCohortCandidateItem(
                    job_id=job.id,
                    title=job.title,
                    company=job.company,
                    area=job.area,
                    salary_min_k=job.salary_min_k,
                    salary_max_k=job.salary_max_k,
                    feedback_id=feedback.feedback_id if feedback else None,
                    decision=decision,
                    feedback_created_at=(feedback.feedback_created_at if feedback else None),
                    reasons=feedback.reasons if feedback else (),
                    note=feedback.note if feedback else None,
                    recommendation=(report.report.recommendation.value if report else None),
                    match_summary=(report.report.summary if report else None),
                )
            )

        return TargetCohortCandidatesResult(
            items=tuple(items),
            total_job_count=page.total,
            total_feedback_records=total_feedback_records,
            latest_job_feedback_count=latest_job_feedback_count,
            excluded_rejected_job_count=len(rejected_job_ids),
            feedback_overlay_available=feedback_overlay_available,
        )


__all__ = [
    "ListTargetCohortCandidatesUseCase",
    "TargetCohortCandidateItem",
    "TargetCohortCandidatesResult",
]
