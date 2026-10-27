"""Deterministic base ranking for persisted MatchReport snapshots."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Literal

from app.application.job_queries.models import JobDetail, JobListItem
from app.application.match_policy_version import CURRENT_MATCH_POLICY_VERSION
from app.application.match_report_history import report_stale_reasons
from app.application.match_report import (
    MatchRecommendation,
    MatchReportPersistenceNotReadyError,
    StoredMatchReport,
)
from app.application.ports.career_context_repository import AbstractCareerContextQueryRepository
from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.application.ports.job_requirement_repository import AbstractJobRequirementQueryRepository
from app.application.ports.match_report_repository import AbstractMatchReportQueryRepository


DEFAULT_TARGET_SUGGESTIONS = 3
MAX_CONFIRMED_TARGETS = 5
MAX_ANALYSIS_JOBS = 50


def is_target_candidate(recommendation: object) -> bool:
    """A readable ranked report is not necessarily an affirmative suggestion."""
    return recommendation in (
        MatchRecommendation.STRONG, MatchRecommendation.GOOD, MatchRecommendation.STRETCH,
    )


def target_suggestion_mode(
    reports: Iterable[StoredMatchReport], job_ids: tuple[str, ...],
) -> Literal["supported", "challenge_only"] | None:
    selected = tuple(item.report.recommendation for item in reports if item.report.job_id in job_ids)
    if not selected:
        return None
    return "challenge_only" if all(item == MatchRecommendation.STRETCH for item in selected) else "supported"


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
    reports = tuple(
        item for item in reports
        if item.report.policy_version == CURRENT_MATCH_POLICY_VERSION
    )
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

    def blocked_hard_gap_count(item: StoredMatchReport) -> int:
        if item.report.recommendation is not MatchRecommendation.BLOCKED:
            return 0
        return len(item.report.missing_requirement_ids)

    return tuple(
        sorted(
            visible,
            key=lambda item: (
                _RECOMMENDATION_PRIORITY[item.report.recommendation],
                -preference_matches(item),
                blocked_hard_gap_count(item),
                item.report.job_id,
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
        requirement_repository: AbstractJobRequirementQueryRepository,
        persistence_ready: Callable[[], bool],
    ) -> None:
        self._report_repository = report_repository
        self._career_context_repository = career_context_repository
        self._job_repository = job_repository
        self._requirement_repository = requirement_repository
        self._persistence_ready = persistence_ready

    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        include_blocked: bool = False,
        top_n: int | None = None,
    ) -> tuple[StoredMatchReport, ...]:
        if not job_ids:
            return ()
        if not self._persistence_ready():
            raise MatchReportPersistenceNotReadyError(
                "MatchReport persistence schema is not ready"
            )

        reports = self._report_repository.list_latest_for_jobs(job_ids)
        if not reports:
            return ()

        current_profile = self._career_context_repository.get_current_profile()
        search_intent = self._career_context_repository.get_current_search_intent()
        report_job_ids = tuple(dict.fromkeys(item.report.job_id for item in reports))
        jobs_by_id = {
            job_id: job for job_id in report_job_ids
            if (job := self._job_repository.get_job(job_id)) is not None
        }
        reports = tuple(item for item in reports if not report_stale_reasons(
            item.report,
            profile=current_profile,
            intent=search_intent,
            extraction=self._requirement_repository.get_latest(item.report.job_id),
            job=jobs_by_id.get(item.report.job_id),
        ))
        ranked = rank_match_reports(
            reports,
            include_blocked=include_blocked,
            soft_preferences=(search_intent.soft_preferences if search_intent is not None else ()),
            jobs_by_id=jobs_by_id,
        )
        return ranked if top_n is None else ranked[:top_n]
