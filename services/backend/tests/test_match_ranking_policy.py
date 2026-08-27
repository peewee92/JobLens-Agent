"""Deterministic Phase 5 MatchReport ranking policy tests."""
from datetime import UTC, datetime

from app.application.eligibility import EligibilityDecision
from app.application.match_report import MatchRecommendation, MatchReport, StoredMatchReport
from app.application.job_queries.models import JobListItem
from app.application.match_ranking import rank_match_reports
from app.domain.jobs import RemoteConfidence, RemoteStatus


def _stored(
    report_id: str,
    recommendation: MatchRecommendation,
    *,
    missing_requirement_count: int = 0,
) -> StoredMatchReport:
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
            missing_requirement_ids=tuple(
                f"req_missing_{report_id}_{index}"
                for index in range(missing_requirement_count)
            ),
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


def test_rank_match_reports_orders_blocked_jobs_with_fewer_hard_gaps_first() -> None:
    reports = (
        _stored("blocked-seven", MatchRecommendation.BLOCKED, missing_requirement_count=7),
        _stored("blocked-one", MatchRecommendation.BLOCKED, missing_requirement_count=1),
        _stored("blocked-three", MatchRecommendation.BLOCKED, missing_requirement_count=3),
    )

    ranked = rank_match_reports(reports, include_blocked=True)

    assert tuple(item.id for item in ranked) == (
        "blocked-one",
        "blocked-three",
        "blocked-seven",
    )


def test_rank_match_reports_keeps_explicit_preference_ahead_of_blocked_gap_count() -> None:
    reports = (
        _stored("plain-one", MatchRecommendation.BLOCKED, missing_requirement_count=1),
        _stored("agent-three", MatchRecommendation.BLOCKED, missing_requirement_count=3),
    )
    jobs = {
        "job_plain-one": _job("job_plain-one", title="Frontend Engineer"),
        "job_agent-three": _job("job_agent-three", title="AI Agent Engineer"),
    }

    ranked = rank_match_reports(
        reports,
        include_blocked=True,
        soft_preferences=("AI Agent",),
        jobs_by_id=jobs,
    )

    assert tuple(item.id for item in ranked) == ("agent-three", "plain-one")


def _job(job_id: str, *, title: str, area: str | None = None) -> JobListItem:
    return JobListItem(
        id=job_id,
        title=title,
        company="Example",
        area=area,
        salary_min_k=None,
        salary_max_k=None,
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
        source="fixture",
        source_url="about:blank",
        source_version=None,
        collected_at=None,
    )


def test_rank_match_reports_uses_explicit_soft_preference_matches_only_within_same_recommendation() -> None:
    reports = (
        _stored("plain-strong", MatchRecommendation.STRONG),
        _stored("agent-good", MatchRecommendation.GOOD),
        _stored("agent-strong", MatchRecommendation.STRONG),
    )
    jobs = {
        "job_plain-strong": _job("job_plain-strong", title="Frontend Engineer"),
        "job_agent-good": _job("job_agent-good", title="AI Agent Engineer"),
        "job_agent-strong": _job("job_agent-strong", title="AI Agent Frontend Engineer"),
    }

    ranked = rank_match_reports(reports, soft_preferences=("AI Agent",), jobs_by_id=jobs)

    assert tuple(item.id for item in ranked) == (
        "agent-strong",
        "plain-strong",
        "agent-good",
    )


def test_rank_match_reports_does_not_match_short_preferences_inside_words() -> None:
    reports = (_stored("embedded", MatchRecommendation.GOOD), _stored("exact", MatchRecommendation.GOOD))
    jobs = {
        "job_embedded": _job("job_embedded", title="Mainframe Engineer"),
        "job_exact": _job("job_exact", title="AI Engineer"),
    }
    ranked = rank_match_reports(reports, soft_preferences=("AI",), jobs_by_id=jobs)
    assert tuple(item.id for item in ranked) == ("exact", "embedded")


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
