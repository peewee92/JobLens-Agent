"""Read-only Phase 5 Batch Ranking application use case tests."""
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.application.career_context.models import SearchIntentDetail
from app.application.eligibility import EligibilityDecision
from app.application.job_queries.models import JobListItem
from app.application.match_ranking import BatchRankMatchReportsUseCase
from app.application.match_report import (
    MatchRecommendation,
    MatchReport,
    MatchReportPersistenceNotReadyError,
    StoredMatchReport,
)
from app.domain.career_context import Seniority
from app.domain.jobs import RemoteConfidence, RemoteStatus


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
            summary="Synthetic batch ranking fixture.",
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


def _job(job_id: str, title: str) -> JobListItem:
    return JobListItem(
        id=job_id,
        title=title,
        company="Example",
        area="Wuhan",
        salary_min_k=None,
        salary_max_k=None,
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
        source="fixture",
        source_url="about:blank",
        source_version=None,
        collected_at=None,
    )


def _intent(*soft_preferences: str) -> SearchIntentDetail:
    return SearchIntentDetail(
        id="intent_1",
        version=1,
        target_roles=(),
        cities=(),
        remote_accepted=None,
        minimum_salary_k=None,
        seniority=Seniority.SENIOR,
        employment_types=(),
        exclude_keywords=(),
        hard_constraints=(),
        soft_preferences=tuple(soft_preferences),
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
    )


def _current_context() -> Mock:
    repo = Mock()
    repo.get_current_profile.return_value = SimpleNamespace(id="profile_1", version=1)
    return repo


def _current_requirements() -> Mock:
    repo = Mock()
    repo.get_latest.side_effect = lambda job_id: SimpleNamespace(
        id=job_id.replace("job_", "reqrun_", 1)
    )
    return repo


def test_batch_ranking_composes_latest_reports_current_preferences_and_job_metadata() -> None:
    report_repo = Mock()
    report_repo.list_latest_for_jobs.return_value = (
        _stored("plain-strong", MatchRecommendation.STRONG),
        _stored("agent-strong", MatchRecommendation.STRONG),
        _stored("blocked", MatchRecommendation.BLOCKED),
    )
    context_repo = _current_context()
    context_repo.get_current_search_intent.return_value = _intent("AI Agent")
    requirement_repo = _current_requirements()
    job_repo = Mock()
    job_repo.get_job.side_effect = lambda job_id: {
        "job_plain-strong": _job("job_plain-strong", "Frontend Engineer"),
        "job_agent-strong": _job("job_agent-strong", "AI Agent Engineer"),
        "job_blocked": _job("job_blocked", "AI Agent Architect"),
    }.get(job_id)

    result = BatchRankMatchReportsUseCase(
        report_repository=report_repo,
        career_context_repository=context_repo,
        job_repository=job_repo,
        requirement_repository=requirement_repo,
        persistence_ready=lambda: True,
    ).execute(("job_plain-strong", "job_agent-strong", "job_blocked"))

    assert tuple(item.id for item in result) == ("agent-strong", "plain-strong")
    report_repo.list_latest_for_jobs.assert_called_once_with(
        ("job_plain-strong", "job_agent-strong", "job_blocked")
    )
    context_repo.get_current_search_intent.assert_called_once_with()
    assert job_repo.get_job.call_count == 3


def test_batch_ranking_is_fail_soft_when_search_intent_or_job_metadata_is_missing() -> None:
    reports = (
        _stored("first", MatchRecommendation.GOOD),
        _stored("second", MatchRecommendation.GOOD),
    )
    report_repo = Mock()
    report_repo.list_latest_for_jobs.return_value = reports
    context_repo = _current_context()
    context_repo.get_current_search_intent.return_value = None
    requirement_repo = _current_requirements()
    job_repo = Mock()
    job_repo.get_job.return_value = None

    result = BatchRankMatchReportsUseCase(
        report_repository=report_repo,
        career_context_repository=context_repo,
        job_repository=job_repo,
        requirement_repository=requirement_repo,
        persistence_ready=lambda: True,
    ).execute(("job_first", "job_second"), include_blocked=True)

    assert result == reports
    assert job_repo.get_job.call_count == 2


def test_batch_ranking_filters_stale_profile_and_requirement_snapshots() -> None:
    current = _stored("current", MatchRecommendation.STRONG)
    stale_profile = _stored("stale-profile", MatchRecommendation.STRONG)
    stale_profile = replace(
        stale_profile,
        report=replace(stale_profile.report, profile_version=0),
    )
    stale_requirement = _stored("stale-requirement", MatchRecommendation.STRONG)

    report_repo = Mock()
    report_repo.list_latest_for_jobs.return_value = (
        current,
        stale_profile,
        stale_requirement,
    )
    context_repo = _current_context()
    context_repo.get_current_search_intent.return_value = None
    requirement_repo = _current_requirements()
    requirement_repo.get_latest.side_effect = lambda job_id: SimpleNamespace(
        id=(
            "reqrun_new"
            if job_id == "job_stale-requirement"
            else job_id.replace("job_", "reqrun_", 1)
        )
    )
    job_repo = Mock()
    job_repo.get_job.return_value = None

    result = BatchRankMatchReportsUseCase(
        report_repository=report_repo,
        career_context_repository=context_repo,
        job_repository=job_repo,
        requirement_repository=requirement_repo,
        persistence_ready=lambda: True,
    ).execute(("job_current", "job_stale-profile", "job_stale-requirement"))

    assert result == (current,)


def test_batch_ranking_returns_only_requested_top_n_after_ranking() -> None:
    report_repo = Mock()
    report_repo.list_latest_for_jobs.return_value = (
        _stored("good", MatchRecommendation.GOOD),
        _stored("strong", MatchRecommendation.STRONG),
        _stored("stretch", MatchRecommendation.STRETCH),
    )
    context_repo = _current_context()
    context_repo.get_current_search_intent.return_value = None
    requirement_repo = _current_requirements()
    job_repo = Mock()
    job_repo.get_job.return_value = None

    result = BatchRankMatchReportsUseCase(
        report_repository=report_repo,
        career_context_repository=context_repo,
        job_repository=job_repo,
        requirement_repository=requirement_repo,
        persistence_ready=lambda: True,
    ).execute(
        ("job_good", "job_strong", "job_stretch"),
        top_n=2,
    )

    assert tuple(item.id for item in result) == ("strong", "good")


def test_batch_ranking_stops_when_no_reports_exist() -> None:
    report_repo = Mock()
    report_repo.list_latest_for_jobs.return_value = ()
    context_repo = Mock()
    requirement_repo = Mock()
    job_repo = Mock()

    result = BatchRankMatchReportsUseCase(
        report_repository=report_repo,
        career_context_repository=context_repo,
        job_repository=job_repo,
        requirement_repository=requirement_repo,
        persistence_ready=lambda: True,
    ).execute(("job_missing",))

    assert result == ()
    report_repo.list_latest_for_jobs.assert_called_once_with(("job_missing",))
    context_repo.get_current_profile.assert_not_called()
    context_repo.get_current_search_intent.assert_not_called()
    job_repo.get_job.assert_not_called()


def test_batch_ranking_fails_closed_before_query_when_persistence_is_not_ready() -> None:
    report_repo = Mock()
    context_repo = Mock()
    requirement_repo = Mock()
    job_repo = Mock()

    with pytest.raises(MatchReportPersistenceNotReadyError):
        BatchRankMatchReportsUseCase(
            report_repository=report_repo,
            career_context_repository=context_repo,
            job_repository=job_repo,
            requirement_repository=requirement_repo,
            persistence_ready=lambda: False,
        ).execute(("job_1",))

    report_repo.list_latest_for_jobs.assert_not_called()
    context_repo.get_current_search_intent.assert_not_called()
    job_repo.get_job.assert_not_called()


def test_batch_ranking_empty_input_does_not_query_other_read_models() -> None:
    report_repo = Mock()
    context_repo = Mock()
    requirement_repo = Mock()
    job_repo = Mock()

    result = BatchRankMatchReportsUseCase(
        report_repository=report_repo,
        career_context_repository=context_repo,
        job_repository=job_repo,
        requirement_repository=requirement_repo,
        persistence_ready=lambda: True,
    ).execute(())

    assert result == ()
    report_repo.list_latest_for_jobs.assert_not_called()
    context_repo.get_current_search_intent.assert_not_called()
    job_repo.get_job.assert_not_called()
