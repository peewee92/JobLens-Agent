"""Deterministic base ranking for persisted MatchReport snapshots."""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from app.application.job_queries.models import JobDetail, JobListItem
from app.application.match_report import MatchRecommendation, StoredMatchReport
from app.application.ports.career_context_repository import AbstractCareerContextQueryRepository
from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.application.ports.match_report_repository import AbstractMatchReportQueryRepository

def _contains_term(text: str, term: str) -> bool:
    start = text.find(term)
    while start >= 0:
        end = start + len(term)
        left_ok = start == 0 or not (text[start - 1].isalnum() or text[start - 1] == "_")
        right_ok = end == len(text) or not (text[end].isalnum() or text[end] == "_")
        if left_ok and right_ok:
            return True
        start = text.find(term, start + 1)
    return False


_RECOMMENDATION_PRIORITY = {
    MatchRecommendation.STRONG: 0,
    MatchRecommendation.GOOD: 1,
    MatchRecommendation.STRETCH: 2,
    MatchRecommendation.LOW: 3,
    MatchRecommendation.BLOCKED: 4,
}


def rank_match_reports(
    reports: Iterable[StoredMatchReport],
    *,
    include_blocked: bool = False,
    soft_preferences: tuple[str, ...] = (),
    jobs_by_id: Mapping[str, JobListItem | JobDetail] | None = None,
) -> tuple[StoredMatchReport, ...]:
    """Return a stable deterministic ranking without mutating source reports."""
    visible = (
        tuple(reports)
        if include_blocked
        else tuple(
            item
            for item in reports
            if item.report.recommendation is not MatchRecommendation.BLOCKED
        )
    )
    normalized_preferences = tuple(
        value.strip().casefold() for value in soft_preferences if value.strip()
    )

    def preference_matches(item: StoredMatchReport) -> int:
        if not normalized_preferences or jobs_by_id is None:
            return 0
        job = jobs_by_id.get(item.report.job_id)
        if job is None:
            return 0
        searchable = " ".join(part for part in (job.title, job.area or "") if part).casefold()
        return sum(_contains_term(searchable, preference) for preference in normalized_preferences)

    return tuple(
        sorted(
            visible,
            key=lambda item: (
                _RECOMMENDATION_PRIORITY[item.report.recommendation],
                -preference_matches(item),
            ),
        )
    )


class BatchRankMatchReportsUseCase:
    """Compose persisted reports and current read models into one ranked batch."""

    def __init__(
        self,
        *,
        report_repository: AbstractMatchReportQueryRepository,
        career_context_repository: AbstractCareerContextQueryRepository,
        job_repository: AbstractJobQueryRepository,
    ) -> None:
        self._report_repository = report_repository
        self._career_context_repository = career_context_repository
        self._job_repository = job_repository

    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        include_blocked: bool = False,
    ) -> tuple[StoredMatchReport, ...]:
        if not job_ids:
            return ()

        reports = self._report_repository.list_latest_for_jobs(job_ids)
        if not reports:
            return ()

        search_intent = self._career_context_repository.get_current_search_intent()
        report_job_ids = tuple(dict.fromkeys(item.report.job_id for item in reports))
        jobs_by_id = {
            job_id: job
            for job_id in report_job_ids
            if (job := self._job_repository.get_job(job_id)) is not None
        }
        return rank_match_reports(
            reports,
            include_blocked=include_blocked,
            soft_preferences=(search_intent.soft_preferences if search_intent is not None else ()),
            jobs_by_id=jobs_by_id,
        )
