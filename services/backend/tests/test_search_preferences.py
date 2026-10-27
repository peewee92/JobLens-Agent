"""Preference rules do not guess career facts or reinterpret unknowns as conflicts."""
from dataclasses import replace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from .test_eligibility_gate import _profile, _extraction, _requirement, _intent, _job, _Readiness, _Requirements, _Jobs
from app.application.eligibility import EvaluateJobEligibilityUseCase, EligibilityDecision, EligibilityInputsNotReadyError
from app.application.search_preferences import evaluate_search_preferences, preference_input_fingerprint
from app.application.match_report import BuildJobMatchReportUseCase, MatchRecommendation
from app.application.match_ranking import BatchRankMatchReportsUseCase
from app.domain.job_requirements import RequirementType, RequirementImportance
from app.domain.jobs import RemoteStatus
from app.api.deps import get_job_eligibility_use_case, get_match_report_use_case
from app.main import app


def _checks(intent, job):
    return {item.key: item for item in evaluate_search_preferences(intent, job)}


@pytest.mark.parametrize("area,remote,accepted,expected", [
    ("武汉·洪山区", RemoteStatus.REJECTED, True, "matched"),
    ("武汉市", RemoteStatus.UNKNOWN, True, "matched"),
    ("上海", RemoteStatus.CONFIRMED, True, "matched"),
    ("上海", RemoteStatus.UNKNOWN, True, "conditional"),
    ("上海", RemoteStatus.REJECTED, True, "missing"),
    ("上海", RemoteStatus.REJECTED, None, "missing"),
    (None, RemoteStatus.REJECTED, True, "conditional"),
    ("全国", RemoteStatus.UNKNOWN, None, "conditional"),
    ("广东省深圳市", RemoteStatus.REJECTED, None, "conditional"),
    ("上海/武汉", RemoteStatus.REJECTED, None, "conditional"),
])
def test_city_and_remote_are_alternatives_not_two_mandatory_conditions(area, remote, accepted, expected):
    checks = _checks(_intent(cities=("武汉",), remote_accepted=accepted), _job(area=area, remote_status=remote))
    assert checks["cities"].status.value == expected
    if accepted is True:
        assert checks["remote"].status.value == "matched"


@pytest.mark.parametrize("remote,expected", [
    (RemoteStatus.CONFIRMED, "missing"),
    (RemoteStatus.REJECTED, "matched"),
    (RemoteStatus.UNKNOWN, "conditional"),
])
def test_explicitly_rejecting_remote_is_distinct_from_accepting_it(remote, expected):
    assert _checks(_intent(remote_accepted=False), _job(remote_status=remote))["remote"].status.value == expected


@pytest.mark.parametrize("low,high,expected", [
    (10, 19, "missing"), (None, 19, "missing"), (20, 25, "matched"),
    (20, None, "matched"), (15, 25, "conditional"), (None, None, "conditional"),
    (30, 15, "conditional"), (-1, 15, "conditional"),
    (float("nan"), 15, "conditional"), (10, float("inf"), "conditional"),
    (None, 25, "conditional"), (10, None, "conditional"),
])
def test_salary_compares_bounds_without_inventing_offer(low, high, expected):
    result = _checks(_intent(minimum_salary_k=20), _job(salary_min_k=low, salary_max_k=high))["salary"]
    assert result.status.value == expected
    assert result.intent_fields == ("minimumSalaryK",)
    assert result.job_fields == ("salaryMinK", "salaryMaxK")


def test_unstructured_constraints_and_unavailable_fields_remain_visible():
    from app.domain.career_context import Seniority
    checks = _checks(_intent(hard_constraints=("不接受长期驻场",),
                            employment_types=("全职",), seniority=Seniority.SENIOR), _job())
    assert set(checks) == {"hardConstraints:0", "employmentTypes", "seniority"}
    assert all(item.status.value == "conditional" for item in checks.values())
    assert "不接受长期驻场" in checks["hardConstraints:0"].reason
    assert checks["hardConstraints:0"].code == "hard_constraint_requires_confirmation"


@pytest.mark.parametrize("word,title,expected", [
    ("Java", "JavaScript Engineer", "matched"),
    ("Java", "Senior Java Engineer", "missing"),
    ("外包", "外包开发", "missing"),
])
def test_exclusion_keywords_have_explicit_search_scope(word, title, expected):
    check = _checks(_intent(exclude_keywords=(word,)), _job(title=title))["excludeKeywords"]
    assert check.status.value == expected
    assert check.job_fields == ("title", "company")


def test_title_difference_is_not_a_hard_role_conflict():
    assert _checks(_intent(target_roles=("AI 工程师",)), _job(title="FDE"))["targetRoles"].status.value == "conditional"


def _use_case(intent=None, job=None):
    profiles = Mock()
    profiles.get_current_profile.return_value = _profile()
    profiles.get_current_search_intent.return_value = intent or _intent(minimum_salary_k=40)
    reqs = _Requirements(_extraction(_requirement(
        0, type=RequirementType.SKILL, text="React", capability="React",
        importance=RequirementImportance.MUST_HAVE,
    )))
    return EvaluateJobEligibilityUseCase(readiness=_Readiness(), profiles=profiles,
                                        requirements=reqs, jobs=_Jobs(job)), profiles


def test_preference_conflict_short_circuits_provider_and_is_visible_on_api():
    eligibility, _ = _use_case()
    result = eligibility.execute("job_1")
    assert result.eligibility is EligibilityDecision.BLOCKED
    assert result.missing_count == 0  # Never invent a JobRequirement for preferences.
    semantic = Mock()
    semantic.execute.side_effect = AssertionError("provider path must not run")
    report_case = BuildJobMatchReportUseCase(semantic, eligibility=eligibility)
    report = report_case.execute("job_1")
    assert report.recommendation is MatchRecommendation.BLOCKED
    assert report.search_intent_id == "intent_1"
    assert report.search_intent_version == 1
    assert report.preference_checks[0].code == "salary_conflict"
    assert report.provider_calls == 0
    semantic.execute.assert_not_called()
    app.dependency_overrides[get_job_eligibility_use_case] = lambda: eligibility
    app.dependency_overrides[get_match_report_use_case] = lambda: report_case
    try:
        with TestClient(app) as client:
            body = client.get("/api/v1/jobs/job_1/eligibility").json()
            saved = client.post("/api/v1/jobs/job_1/match-report").json()
        assert body["preferenceChecks"][0]["status"] == "missing"
        assert saved["preferenceChecks"] == body["preferenceChecks"]
        assert saved["searchIntentId"] == "intent_1"
    finally:
        app.dependency_overrides.clear()


def test_intent_change_after_readiness_is_rejected_before_work():
    case, profiles = _use_case()
    profiles.get_current_search_intent.return_value = _intent(version=2)
    with pytest.raises(EligibilityInputsNotReadyError, match="changed after readiness"):
        case.execute("job_1")


@pytest.mark.parametrize("change", ["intent", "salary", "city", "remote", "missing_binding"])
def test_ranking_rejects_stale_preference_inputs_without_rewriting_report(change):
    from .test_batch_match_ranking_use_case import _stored, _job as ranking_job, _intent as ranking_intent
    intent = ranking_intent()
    job = ranking_job("job_current", "Engineer")
    stored = _stored("current", MatchRecommendation.GOOD, intent=intent, job=job)
    context = Mock()
    context.get_current_profile.return_value = _profile()
    context.get_current_search_intent.return_value = intent
    reqs = Mock()
    reqs.get_latest.return_value = type("Extraction", (), {"extraction_id": "reqrun_current"})()
    reports, jobs = Mock(), Mock()
    reports.list_latest_for_jobs.return_value = (stored,)
    jobs.get_job.return_value = job
    ranking = BatchRankMatchReportsUseCase(report_repository=reports, career_context_repository=context,
                                          requirement_repository=reqs, job_repository=jobs, persistence_ready=lambda: True)
    assert ranking.execute((job.id,)) == (stored,)
    original = stored.report
    if change == "intent":
        context.get_current_search_intent.return_value = replace(intent, version=2)
    elif change == "missing_binding":
        reports.list_latest_for_jobs.return_value = (replace(stored, report=replace(stored.report, preference_fingerprint=None)),)
    else:
        attr, value = {"salary": ("salary_max_k", 50), "city": ("area", "上海"),
                       "remote": ("remote_status", RemoteStatus.CONFIRMED)}[change]
        jobs.get_job.return_value = replace(job, **{attr: value})
    assert ranking.execute((job.id,)) == ()
    assert stored.report == original
