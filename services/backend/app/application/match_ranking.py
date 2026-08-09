"""Deterministic base ranking for persisted MatchReport snapshots."""
from __future__ import annotations

from collections.abc import Iterable

from app.application.match_report import MatchRecommendation, StoredMatchReport

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
) -> tuple[StoredMatchReport, ...]:
    """Return a stable recommendation-ordered view without mutating source reports."""
    visible = (
        tuple(reports)
        if include_blocked
        else tuple(
            item
            for item in reports
            if item.report.recommendation is not MatchRecommendation.BLOCKED
        )
    )
    return tuple(
        sorted(
            visible,
            key=lambda item: _RECOMMENDATION_PRIORITY[item.report.recommendation],
        )
    )
