"""Deterministic base ranking for persisted MatchReport snapshots."""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from app.application.job_queries.models import JobListItem
from app.application.match_report import MatchRecommendation, StoredMatchReport

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
    jobs_by_id: Mapping[str, JobListItem] | None = None,
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
