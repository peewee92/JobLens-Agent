"""Changed job text must invalidate matching without destroying old results."""
from unittest.mock import Mock
from sqlalchemy import text
from app.workflows.semantic_match import SemanticMatchWorkflow
from .test_career_agent_analysis_snapshot import synthetic_api, start, approve


def test_revoked_requirement_trace_is_excluded_before_target_confirmation(synthetic_api):
    client, factory, ids = synthetic_api
    before = client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items'][0]
    state = start(client, ids, 'trace_revoked_during_confirmation')
    with factory.begin() as session:
        session.execute(text('UPDATE trace_spans SET error=:error WHERE id=(SELECT trace_run_id FROM job_requirement_extractions WHERE job_id=:id ORDER BY created_at DESC LIMIT 1)'),
            {'error': 'synthetic failure', 'id': ids[0]})
    readiness = client.get(f'/api/v1/jobs/{ids[0]}/match-input-readiness').json()
    assert readiness['inputsReleaseEligible'] is False
    response = client.get('/api/v1/match-ranking/preflight', params=[('jobId', ids[0]), ('jobId', ids[1])])
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item['jobId'] for item in body['items']] == [ids[1]]
    assert any(item['jobId'] == ids[0] and 'requirements_not_released' in item['staleReasons'] for item in body['omissions'])
    history = client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items'][0]
    assert history['isCurrent'] is False and history['staleReasons'] == ['requirements_not_released']
    assert history['report'] == before['report']
    from jsonschema import Draft202012Validator
    from pathlib import Path
    import json
    schema = json.loads((Path(__file__).parents[3] / 'packages/contracts/schemas/match-report-history.schema.json').read_text())
    Draft202012Validator(schema['properties']['items']['items']['properties']['staleReasons']).validate(history['staleReasons'])
    resumed = approve(client, state)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['status'] == 'stale'
    assert client.get(f'/api/v1/career-agent/runs/{state["threadId"]}/result').status_code == 404


def test_changed_description_blocks_ranking_and_marks_saved_result_historical(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    forbidden = Mock(side_effect=AssertionError('no model during read or ranking'))
    monkeypatch.setattr(SemanticMatchWorkflow, 'execute', forbidden)
    before = client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items'][0]
    assert before['isCurrent'] is True
    state = start(client, ids, 'description_change')
    completed = approve(client, state)
    assert completed.status_code == 200, completed.text
    original = client.get('/api/v1/career-agent/runs/description_change/result').json()
    assert original['isCurrent'] is True
    with factory.begin() as session:
        session.execute(text('UPDATE jobs SET description=:description WHERE id=:id'),
            {'description': 'A newly observed synthetic job description with materially different requirements.', 'id': ids[0]})
    readiness = client.get(f'/api/v1/jobs/{ids[0]}/requirement-release-readiness').json()
    assert any(b['code'] == 'extraction_input_stale' for b in readiness['blockers'])
    history = client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items'][0]
    assert not history['isCurrent'] and 'job_description_changed' in history['staleReasons']
    assert history['report'] == before['report']
    preflight = client.get('/api/v1/match-ranking/preflight', params=[('jobId', ids[0]), ('jobId', ids[1])]).json()
    # This seed's accepted baseline contains the changed job; its current
    # implementation invalidates that global baseline for the other job too.
    assert not preflight['items']
    assert any(item['jobId'] == ids[1] and 'requirements_not_released' in item['staleReasons'] for item in preflight['omissions'])
    assert any(item['jobId'] == ids[0] and item['reason'] == 'report_stale'
        and 'job_description_changed' in item['staleReasons'] for item in preflight['omissions'])
    current = client.get('/api/v1/career-agent/runs/description_change/result').json()
    assert not current['isCurrent'] and any('job_description_changed' in reason for reason in current['staleReasons'])
    assert current['resultId'] == original['resultId'] and current['preparations'] == original['preparations']
    forbidden.assert_not_called()


def test_real_reimport_of_changed_text_excludes_old_report(synthetic_api):
    from copy import deepcopy
    from sqlalchemy import select
    from app.application.job_imports.adapter import adapt_collector_report
    from app.application.job_imports.normalizer import normalize_adapted_report
    from app.db.models import JobORM, JobSourceORM, JobImportItemORM
    from .test_job_import_api import load_report

    client, factory, ids = synthetic_api
    report = load_report()
    job_input = normalize_adapted_report(adapt_collector_report(report)).jobs[0]
    with factory.begin() as session:
        job = session.get(JobORM, ids[0])
        source = session.scalar(select(JobSourceORM).where(JobSourceORM.job_id == ids[0]))
        job.canonical_key = job_input.canonical_key
        job.canonical_key_version = job_input.canonical_key_version
        source.source = job_input.source
        source.source_job_id = job_input.source_job_id
        source.source_url = job_input.source_url
        source.normalized_source_url = job_input.normalized_source_url
    original = client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items'][0]
    assert original['isCurrent']
    report = deepcopy(report)
    report['jobs'][0]['description'] = '更新后的岗位描述仅作为合成测试数据。'
    response = client.post('/api/v1/job-imports', json=report)
    assert response.status_code == 201, response.text
    assert response.json()['updated'] == 1
    with factory() as session:
        item = session.scalar(select(JobImportItemORM).where(JobImportItemORM.import_id == response.json()['importId']))
        assert item.job_id == ids[0]
        assert item.source_raw_snapshot == report['jobs'][0]
    history = client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items'][0]
    assert not history['isCurrent'] and 'job_description_changed' in history['staleReasons']
    assert history['report'] == original['report']
    ranking = client.get('/api/v1/match-ranking/preflight', params={'jobId': ids[0]}).json()
    assert not ranking['items'] and 'job_description_changed' in ranking['omissions'][0]['staleReasons']


def test_outer_whitespace_only_does_not_invalidate_current_requirements(synthetic_api):
    client, factory, ids = synthetic_api
    with factory.begin() as session:
        session.execute(text("UPDATE jobs SET description = '  ' || description || '  ' WHERE id=:id"), {'id': ids[0]})
    history = client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items'][0]
    assert history['isCurrent'] is True
    assert client.get('/api/v1/match-ranking/preflight', params={'jobId': ids[0]}).json()['items']


def test_stale_reason_is_in_shared_history_contract(synthetic_api):
    import json
    from pathlib import Path
    from jsonschema import Draft202012Validator

    client, factory, ids = synthetic_api
    with factory.begin() as session:
        session.execute(text('UPDATE jobs SET description=:value WHERE id=:id'),
            {'value': 'Changed synthetic text', 'id': ids[0]})
    item = client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items'][0]
    schema = json.loads((Path(__file__).parents[3] / 'packages/contracts/schemas/match-report-history.schema.json').read_text())
    reason_schema = schema['properties']['items']['items']['properties']['staleReasons']
    Draft202012Validator(reason_schema).validate(item['staleReasons'])


def test_changed_description_before_approval_stops_resume_without_result(synthetic_api, monkeypatch):
    from app.application.saved_career_analysis import BuildSavedCareerAnalysisUseCase
    from app.repositories.sqlalchemy_career_agent_checkpoint import SqlAlchemyCareerAgentCheckpointStore

    client, factory, ids = synthetic_api
    state = start(client, ids, 'description_before_approval')
    with factory.begin() as session:
        session.execute(text('UPDATE jobs SET description=:value WHERE id=:id'),
            {'value': 'Changed synthetic requirements during approval', 'id': ids[0]})
    forbidden = Mock(side_effect=AssertionError('stale inputs must not generate materials'))
    monkeypatch.setattr(BuildSavedCareerAnalysisUseCase, 'execute', forbidden)
    result = approve(client, state)
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'stale'
    assert result.json()['currentStep'] == 'resume_stale_match_reports'
    assert SqlAlchemyCareerAgentCheckpointStore(factory).load_analysis(thread_id='description_before_approval') is None
    assert client.get('/api/v1/career-agent/runs/description_before_approval/result').status_code == 404
    forbidden.assert_not_called()


def test_changed_description_during_compute_never_produces_current_result(synthetic_api, monkeypatch):
    from app.application.saved_career_analysis import BuildSavedCareerAnalysisUseCase

    client, factory, ids = synthetic_api
    state = start(client, ids, 'description_during_compute')
    execute = BuildSavedCareerAnalysisUseCase.execute
    def compute_then_update(self, **kwargs):
        result = execute(self, **kwargs)
        with factory.begin() as session:
            session.execute(text('UPDATE jobs SET description=:value WHERE id=:id'),
                {'value': 'Changed synthetic requirements during computation', 'id': ids[0]})
        return result
    monkeypatch.setattr(BuildSavedCareerAnalysisUseCase, 'execute', compute_then_update)
    response = approve(client, state)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'stale'
    assert response.json()['currentStep'] == 'analysis_facts_changed'
    saved = client.get('/api/v1/career-agent/runs/description_during_compute/result').json()
    assert not saved['isCurrent']
    assert any('job_description_changed' in code for code in saved['staleReasons'])
    assert saved['resultId'] == response.json()['resultId']


def test_incomplete_repository_projection_is_excluded_from_http_ranking(synthetic_api, monkeypatch):
    from app.application.job_queries.models import JobListItem
    from app.repositories.sqlalchemy_job_query_repository import SqlAlchemyJobQueryRepository

    client, _, ids = synthetic_api
    original = SqlAlchemyJobQueryRepository.get_job
    def incomplete(self, job_id):
        detail = original(self, job_id)
        if job_id != ids[0] or detail is None:
            return detail
        return JobListItem(**{name: getattr(detail, name) for name in JobListItem.__dataclass_fields__})
    monkeypatch.setattr(SqlAlchemyJobQueryRepository, 'get_job', incomplete)
    response = client.get('/api/v1/match-ranking/preflight', params=[('jobId', ids[0]), ('jobId', ids[1])])
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item['jobId'] for item in body['items']] == [ids[1]]
    assert body['omissions'][0]['jobId'] == ids[0]
    assert 'job_description_unavailable' in body['omissions'][0]['staleReasons']
