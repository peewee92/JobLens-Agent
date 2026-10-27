"""History is an original snapshot, never an implicit new analysis."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.deps import get_match_report_history_use_case
from app.application.job_queries import JobNotFoundError
from app.application.match_report import MatchReportPersistenceNotReadyError, MatchRecommendation
from app.application.match_report_history import GetMatchReportHistoryUseCase, report_stale_reasons
from app.application.search_preferences import preference_input_fingerprint
from app.main import app
from app.repositories.sqlalchemy_match_report_repository import SqlAlchemyMatchReportQueryRepository
from app.repositories.sqlalchemy_match_report_unit_of_work import SqlAlchemyMatchReportUnitOfWork
from .test_batch_match_ranking_use_case import _intent, _job, _stored
from .test_match_report_repository import _factory


def _setup(tmp_path):
    factory = _factory(tmp_path)
    intent = _intent()
    job = _job("job_1", "Engineer")
    report = replace(_stored("1", MatchRecommendation.LOW).report,
                     search_intent_id=intent.id, search_intent_version=intent.version,
                     preference_fingerprint=preference_input_fingerprint(intent, job))
    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        old = uow.reports.add(replace(report, policy_version="match-policy-v2", summary="原有结论"))
        uow.commit()
    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        current = uow.reports.add(report)
        uow.commit()
    context = Mock()
    context.get_current_profile.return_value = SimpleNamespace(id="profile_1", version=1)
    context.get_current_search_intent.return_value = intent
    jobs = Mock()
    jobs.get_job.side_effect = lambda key: job if key == job.id else None
    requirements = Mock()
    requirements.get_latest.return_value = SimpleNamespace(extraction_id="reqrun_1")
    use_case = GetMatchReportHistoryUseCase(
        reports=SqlAlchemyMatchReportQueryRepository(factory), context=context,
        jobs=jobs, requirements=requirements, persistence_ready=lambda: True,
    )
    return factory, use_case, context, requirements, old, current


def test_history_sqlite_preserves_old_results_and_performs_only_reads(tmp_path):
    factory, use_case, context, _, old, current = _setup(tmp_path)
    statements = []
    event.listen(factory.kw["bind"], "before_cursor_execute",
                 lambda _conn, _cursor, statement, *_: statements.append(statement))
    entries = use_case.execute("job_1")
    assert [item.stored.id for item in entries] == [current.id, old.id]
    assert entries[0].stale_reasons == ()
    assert entries[1].stale_reasons == ("policy_changed",)
    assert entries[1].stored.report.summary == "原有结论"
    context.get_current_profile.return_value = SimpleNamespace(id="profile_1", version=2)
    changed = use_case.execute("job_1")
    assert "profile_changed" in changed[0].stale_reasons
    assert changed[0].stored == entries[0].stored
    assert statements and all(sql.lstrip().upper().startswith("SELECT") for sql in statements)


def test_history_works_without_current_context_but_missing_job_is_not_history(tmp_path):
    _, use_case, context, requirements, _, _ = _setup(tmp_path)
    context.get_current_profile.return_value = None
    context.get_current_search_intent.return_value = None
    requirements.get_latest.return_value = None
    reasons = use_case.execute("job_1")[0].stale_reasons
    assert reasons == ("profile_missing", "search_intent_missing", "requirements_missing")
    with pytest.raises(JobNotFoundError):
        use_case.execute("other_job")
    use_case._persistence_ready = lambda: False
    with pytest.raises(MatchReportPersistenceNotReadyError):
        use_case.execute("job_1")


@pytest.mark.parametrize("change, expected", [
    ("profile_identity", "profile_changed"), ("intent_identity", "search_intent_changed"),
    ("intent_version", "search_intent_changed"), ("extraction", "requirements_changed"),
    ("job_metadata", "preference_inputs_changed"), ("job_missing", "job_missing"),
])
def test_currentness_covers_identity_version_and_preference_inputs(change, expected):
    intent = _intent()
    job = _job("job_1", "Engineer")
    report = replace(_stored("1", MatchRecommendation.GOOD, intent=intent, job=job).report)
    profile = SimpleNamespace(id="profile_1", version=1)
    extraction = SimpleNamespace(extraction_id="reqrun_1")
    if change == "profile_identity": profile.id = "other_profile"
    if change == "intent_identity": intent = replace(intent, id="other_intent")
    if change == "intent_version": intent = replace(intent, version=2)
    if change == "extraction": extraction.extraction_id = "reqrun_other"
    if change == "job_metadata": job = replace(job, salary_min_k=50)
    if change == "job_missing": job = None
    assert expected in report_stale_reasons(report, profile=profile, intent=intent, extraction=extraction, job=job)


def test_history_http_returns_original_nested_snapshot_and_currentness(tmp_path):
    _, use_case, context, _, old, current = _setup(tmp_path)
    app.dependency_overrides[get_match_report_history_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/jobs/job_1/match-reports")
            assert response.status_code == 200
            body = response.json()
            assert body["count"] == 2
            assert body["items"][0]["reportId"] == current.id
            assert body["items"][0]["isCurrent"] is True
            assert body["items"][1]["reportId"] == old.id
            assert body["items"][1]["report"]["summary"] == "原有结论"
            assert body["items"][1]["staleReasons"] == ["policy_changed"]
            context.get_current_profile.return_value = None
            assert client.get("/api/v1/jobs/job_1/match-reports").json()["items"][0]["isCurrent"] is False
            assert client.get("/api/v1/jobs/other_job/match-reports").status_code == 404
    finally:
        app.dependency_overrides.pop(get_match_report_history_use_case, None)
