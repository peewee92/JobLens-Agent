"""Read-only Phase 5 Batch Ranking application use case tests."""
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from hashlib import sha256

import pytest

from app.application.career_context.models import SearchIntentDetail
from app.application.eligibility import EligibilityDecision
from app.application.job_queries.models import JobDetail
from app.application.match_ranking import BatchRankMatchReportsUseCase
from app.application.search_preferences import preference_input_fingerprint
from app.application.evidence_retrieval.strategy import RETRIEVAL_VERSION
from app.application.match_report import (
    MatchRecommendation,
    MatchReport,
    MatchReportPersistenceNotReadyError,
    StoredMatchReport,
)
from app.domain.career_context import Seniority
from app.domain.jobs import RemoteConfidence, RemoteStatus


def _stored(report_id: str, recommendation: MatchRecommendation, *, intent=None, job=None) -> StoredMatchReport:
    return StoredMatchReport(
        id=report_id,
        report=MatchReport(
            job_id=f"job_{report_id}",
            search_intent_id=intent.id if intent else None,
            search_intent_version=intent.version if intent else None,
            preference_fingerprint=preference_input_fingerprint(intent, job) if intent and job else None,
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
            retrieval_version=RETRIEVAL_VERSION,
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


def _job(job_id: str, title: str) -> JobDetail:
    return JobDetail(
        id=job_id,
        title=title,
        company="Example",
        area="Wuhan",
        salary_min_k=None,
        salary_max_k=None,
        experience=None,
        education=None,
        description=None,
        skills=(),
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
        source="fixture",
        source_url="about:blank",
        source_version=None,
        description_quality=None,
        requirement_review_eligible=None,
        requirement_review_ineligibility_reasons=(),
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
        extraction_id=job_id.replace("job_", "reqrun_", 1), input_hash=sha256(b"").hexdigest()
    )
    return repo


def test_batch_ranking_composes_latest_reports_current_preferences_and_job_metadata() -> None:
    report_repo = Mock()
    report_repo.list_latest_for_jobs.return_value = (
        _stored("plain-strong", MatchRecommendation.STRONG, intent=_intent("AI Agent"), job=_job("job_plain-strong", "Frontend Engineer")),
        _stored("agent-strong", MatchRecommendation.STRONG, intent=_intent("AI Agent"), job=_job("job_agent-strong", "AI Agent Engineer")),
        _stored("blocked", MatchRecommendation.BLOCKED, intent=_intent("AI Agent"), job=_job("job_blocked", "AI Agent Architect")),
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
        requirement_release=Mock(execute=Mock(return_value=Mock(release_eligible=True))), persistence_ready=lambda: True,
    ).execute(("job_plain-strong", "job_agent-strong", "job_blocked"))

    assert tuple(item.id for item in result) == ("agent-strong", "plain-strong")
    report_repo.list_latest_for_jobs.assert_called_once_with(
        ("job_plain-strong", "job_agent-strong", "job_blocked")
    )
    context_repo.get_current_search_intent.assert_called_once_with()
    assert job_repo.get_job.call_count == 3


def test_batch_ranking_requires_current_intent_and_job_facts() -> None:
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
        requirement_release=Mock(execute=Mock(return_value=Mock(release_eligible=True))), persistence_ready=lambda: True,
    ).execute(("job_first", "job_second"), include_blocked=True)

    assert result == ()
    assert job_repo.get_job.call_count == 2


def test_batch_ranking_filters_stale_profile_and_requirement_snapshots() -> None:
    current = _stored("current", MatchRecommendation.STRONG, intent=_intent(), job=_job("job_current", "Engineer"))
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
    context_repo.get_current_search_intent.return_value = _intent()
    requirement_repo = _current_requirements()
    requirement_repo.get_latest.side_effect = lambda job_id: SimpleNamespace(
        input_hash=sha256(b"").hexdigest(),
        extraction_id=(
            "reqrun_new"
            if job_id == "job_stale-requirement"
            else job_id.replace("job_", "reqrun_", 1)
        )
    )
    job_repo = Mock()
    job_repo.get_job.side_effect = lambda job_id: _job(job_id, "Engineer")

    result = BatchRankMatchReportsUseCase(
        report_repository=report_repo,
        career_context_repository=context_repo,
        job_repository=job_repo,
        requirement_repository=requirement_repo,
        requirement_release=Mock(execute=Mock(return_value=Mock(release_eligible=True))), persistence_ready=lambda: True,
    ).execute(("job_current", "job_stale-profile", "job_stale-requirement"))

    assert result == (current,)


def test_batch_ranking_returns_only_requested_top_n_after_ranking() -> None:
    report_repo = Mock()
    report_repo.list_latest_for_jobs.return_value = (
        _stored("good", MatchRecommendation.GOOD, intent=_intent(), job=_job("job_good", "Engineer")),
        _stored("strong", MatchRecommendation.STRONG, intent=_intent(), job=_job("job_strong", "Engineer")),
        _stored("stretch", MatchRecommendation.STRETCH, intent=_intent(), job=_job("job_stretch", "Engineer")),
    )
    context_repo = _current_context()
    context_repo.get_current_search_intent.return_value = _intent()
    requirement_repo = _current_requirements()
    job_repo = Mock()
    job_repo.get_job.side_effect = lambda job_id: _job(job_id, "Engineer")

    result = BatchRankMatchReportsUseCase(
        report_repository=report_repo,
        career_context_repository=context_repo,
        job_repository=job_repo,
        requirement_repository=requirement_repo,
        requirement_release=Mock(execute=Mock(return_value=Mock(release_eligible=True))), persistence_ready=lambda: True,
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
        requirement_release=Mock(execute=Mock(return_value=Mock(release_eligible=True))), persistence_ready=lambda: True,
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
            requirement_release=Mock(execute=Mock(return_value=Mock(release_eligible=True))), persistence_ready=lambda: False,
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
        requirement_release=Mock(execute=Mock(return_value=Mock(release_eligible=True))), persistence_ready=lambda: True,
    ).execute(())

    assert result == ()
    report_repo.list_latest_for_jobs.assert_not_called()
    context_repo.get_current_search_intent.assert_not_called()
    job_repo.get_job.assert_not_called()


def test_preflight_uses_same_ranking_and_explains_each_omission() -> None:
    intent = _intent()
    def report(name, recommendation):
        return _stored(name, recommendation, intent=intent, job=_job(f"job_{name}", "Engineer"))
    current = report("current", MatchRecommendation.GOOD)
    blocked = report("blocked", MatchRecommendation.BLOCKED)
    stale = report("stale", MatchRecommendation.STRONG)
    stale = replace(stale, report=replace(stale.report, profile_version=0))
    reports = Mock()
    reports.list_latest_for_jobs.return_value = (current, blocked, stale)
    context = _current_context()
    context.get_current_search_intent.return_value = intent
    jobs = Mock()
    jobs.get_job.side_effect = lambda job_id: _job(job_id, "Engineer")
    use_case = BatchRankMatchReportsUseCase(report_repository=reports, career_context_repository=context,
        job_repository=jobs, requirement_repository=_current_requirements(), requirement_release=Mock(execute=Mock(return_value=Mock(release_eligible=True))), persistence_ready=lambda: True)
    ids = ("job_current", "job_missing", "job_stale", "job_blocked")
    ranked, omitted = use_case.preflight(ids)
    assert ranked == use_case.execute(ids) == (current,)
    assert [(x.job_id, x.reason, x.stale_reasons) for x in omitted] == [
        ("job_missing", "report_missing", ()), ("job_stale", "report_stale", ("profile_changed",)),
        ("job_blocked", "hard_conflict", ()),
    ]


def test_ranking_fails_closed_when_repository_returns_only_list_projection():
    from app.application.job_queries.models import JobListItem

    intent = _intent()
    detail = _job('job_1', 'Engineer')
    projection = JobListItem(**{name: getattr(detail, name) for name in JobListItem.__dataclass_fields__})
    reports = Mock()
    reports.list_latest_for_jobs.return_value = (_stored('1', MatchRecommendation.GOOD, intent=intent, job=detail),)
    context = _current_context()
    context.get_current_search_intent.return_value = intent
    jobs = Mock()
    jobs.get_job.return_value = projection
    use_case = BatchRankMatchReportsUseCase(report_repository=reports, career_context_repository=context,
        job_repository=jobs, requirement_repository=_current_requirements(), requirement_release=Mock(execute=Mock(return_value=Mock(release_eligible=True))), persistence_ready=lambda: True)
    ranked, omissions = use_case.preflight(('job_1',))
    assert not ranked
    assert omissions[0].reason == 'report_stale'
    assert 'job_description_unavailable' in omissions[0].stale_reasons
