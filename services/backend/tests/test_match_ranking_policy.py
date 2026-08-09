"""Deterministic Phase 5 MatchReport ranking policy tests."""
from datetime import UTC, datetime

from app.application.eligibility import EligibilityDecision
from app.application.match_report import MatchRecommendation, MatchReport, StoredMatchReport
from app.application.match_ranking import rank_match_reports


def _stored(report_id: str, recommendation: MatchRecommendation) -> StoredMatchReport:
    return StoredMatchReport(
        id=report_id,
        report=MatchReport(
            job_id=f"job_{report_id}",
            profile_id="profile_1",
            profile_version=1,
            extraction_id=f"reqrun_{report_id}",
            eligibility=(
                EligibilityDecision.BLOCKED
                if recommendation is MatchRecommendation.BLOCKED
                else EligibilityDecision.ELIGIBLE
            ),
            recommendation=recommendation,
            summary="Synthetic ranking fixture.",
            strengths=(),
            risks=(),
            requirement_results=(),
            matched_requirement_ids=(),
            partial_requirement_ids=(),
            missing_requirement_ids=(),
            evidence_links=(),
            matcher_version="semantic-match-v1",
            prompt_version="semantic-match-v3",
            model="fixture",
            trace_run_id=None,
        ),
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
    )


def test_rank_match_reports_orders_recommendations_and_hides_blocked_by_default() -> None:
    reports = (
        _stored("low", MatchRecommendation.LOW),
        _stored("blocked", MatchRecommendation.BLOCKED),
        _stored("strong", MatchRecommendation.STRONG),
        _stored("stretch", MatchRecommendation.STRETCH),
        _stored("good", MatchRecommendation.GOOD),
    )

    ranked = rank_match_reports(reports)

    assert tuple(item.id for item in ranked) == ("strong", "good", "stretch", "low")


def test_rank_match_reports_can_include_blocked_only_at_the_end() -> None:
    reports = (
        _stored("blocked-a", MatchRecommendation.BLOCKED),
        _stored("good", MatchRecommendation.GOOD),
        _stored("blocked-b", MatchRecommendation.BLOCKED),
        _stored("strong", MatchRecommendation.STRONG),
    )

    ranked = rank_match_reports(reports, include_blocked=True)

    assert tuple(item.id for item in ranked) == (
        "strong",
        "good",
        "blocked-a",
        "blocked-b",
    )


def test_rank_match_reports_is_stable_for_equal_recommendations_and_does_not_mutate_input() -> None:
    reports = (
        _stored("good-first", MatchRecommendation.GOOD),
        _stored("strong", MatchRecommendation.STRONG),
        _stored("good-second", MatchRecommendation.GOOD),
    )
    original = tuple(reports)

    ranked = rank_match_reports(reports)

    assert tuple(item.id for item in ranked) == (
        "strong",
        "good-first",
        "good-second",
    )
    assert reports == original
