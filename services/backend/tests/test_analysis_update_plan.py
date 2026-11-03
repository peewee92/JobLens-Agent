"""Actual original run -> read-only current-scope plan; no Match/Provider execution."""
import json
from pathlib import Path
import sqlite3
from unittest.mock import Mock
from sqlalchemy import select

from .test_career_agent_analysis_snapshot import synthetic_api, approve
from app.workflows.semantic_match import SemanticMatchWorkflow
from app.db.models import UserProfileORM


def _source(client, ids):
    response = client.post('/api/v1/career-agent/runs', json=dict(threadId='update_source',
        runId='update_run', requestId='update_request', jobIds=ids[:8], topN=2))
    assert response.status_code == 200, response.text
    confirmed = approve(client, response.json())
    assert confirmed.status_code == 200 and confirmed.json()['status'] == 'completed', confirmed.text
    return client.get('/api/v1/career-agent/runs/update_source/result').json()


def _profile(client, *, semantic=False):
    response = client.put('/api/v1/profile', json=dict(expectedVersion=1, headline='Synthetic updated verified facts',
        yearsOfExperience=5, evidence=[dict(key='actual', type='project', summary='Implemented a Python backend outcome', source='Synthetic test repository')],
        skills=[dict(name='TypeScript' if semantic else 'Python', level='strong', evidenceKeys=['actual'])]))
    assert response.status_code == 200, response.text
    return response.json()


def _dump(factory):
    with sqlite3.connect(factory.kw['bind'].url.database) as connection:
        return tuple(connection.iterdump())


def test_scopes_use_original_batch_and_confirmed_targets_without_writes_or_match_execution(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    saved = _source(client, ids)
    forbidden = Mock(side_effect=AssertionError('planning may not call Match/Provider'))
    monkeypatch.setattr(SemanticMatchWorkflow, 'execute', forbidden)
    before = _dump(factory)
    target = client.get('/api/v1/career-agent/runs/update_source/update-plan')
    assert target.status_code == 200, target.text
    data = target.json()
    assert data['sourceResultId'] == saved['resultId'] and data['advisoryOnly'] is True
    assert [i['jobId'] for i in data['items']] == saved['selectedJobIds']
    assert len(data['reusableJobIds']) == 2 and not data['nextJobIds']
    batch = client.get('/api/v1/career-agent/runs/update_source/update-plan?scope=batch').json()
    assert [i['jobId'] for i in batch['items']] == ids[:8]
    assert len(batch['reusableJobIds']) == 8
    assert all(i['status'] == 'reuse' and i['reusableReportId'] for i in batch['items'])
    assert _dump(factory) == before
    forbidden.assert_not_called()


def test_changed_profile_limits_new_analyses_to_five_and_preserves_original_result(synthetic_api):
    client, factory, ids = synthetic_api
    original = _source(client, ids)
    updated = _profile(client)
    before = _dump(factory)
    data = client.get('/api/v1/career-agent/runs/update_source/update-plan?scope=batch').json()
    assert data['previousProfileVersion'] == 1 and data['profileVersion'] == 2
    assert data['profileId'] == updated['id']
    assert data['nextJobIds'] == ids[:5] and data['maxNewAnalyses'] == 5
    assert [i['status'] for i in data['items']] == ['ready'] * 5 + ['deferred'] * 3
    assert all('profile_changed' in i['staleReasons'] for i in data['items'])
    assert _dump(factory) == before
    reopened = client.get('/api/v1/career-agent/runs/update_source/result').json()
    assert reopened['preparations'] == original['preparations'] and reopened['profileVersion'] == 1
    assert not reopened['isCurrent']
    assert client.get('/api/v1/career-agent/runs/update_source').json()['status'] == 'completed'


def test_requires_semantic_model_is_explicit_and_never_called(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    _source(client, ids)
    _profile(client, semantic=True)
    forbidden = Mock(side_effect=AssertionError('no model authorization'))
    monkeypatch.setattr(SemanticMatchWorkflow, 'execute', forbidden)
    before = _dump(factory)
    response = client.get('/api/v1/career-agent/runs/update_source/update-plan')
    assert response.status_code == 200, response.text
    data = response.json()
    assert not data['nextJobIds']
    assert all(i['status'] == 'requires_model' and i['requiredOperations'] == ['semantic_match']
               and 'model_authorization_required' in i['blockerCodes'] for i in data['items'])
    assert _dump(factory) == before
    forbidden.assert_not_called()


def test_valid_new_report_is_reused_while_others_remain_bounded(synthetic_api):
    client, factory, ids = synthetic_api
    _source(client, ids)
    _profile(client)
    new = client.post(f'/api/v1/jobs/{ids[0]}/match-report')
    assert new.status_code == 200, new.text
    before = _dump(factory)
    data = client.get('/api/v1/career-agent/runs/update_source/update-plan?scope=batch').json()
    assert data['reusableJobIds'] == ids[:1] and data['nextJobIds'] == ids[1:6]
    assert data['items'][0]['status'] == 'reuse'
    assert [i['status'] for i in data['items'][-2:]] == ['deferred', 'deferred']
    assert _dump(factory) == before


def test_missing_original_and_invalid_scope_are_not_an_empty_success(synthetic_api):
    client, factory, ids = synthetic_api
    assert client.get('/api/v1/career-agent/runs/unknown/update-plan').status_code == 404
    assert client.get('/api/v1/career-agent/runs/unknown/update-plan?scope=all_jobs').status_code == 422


def test_update_plan_shared_contract_matches_python():
    from app.api.v1.schemas.analysis_update import AnalysisUpdatePlanResponse
    schema = json.loads((Path(__file__).parents[3] / 'packages/contracts/schemas/analysis-update-plan.schema.json').read_text())
    del schema['$schema'], schema['$id']
    assert schema == AnalysisUpdatePlanResponse.model_json_schema(by_alias=True)


def test_one_version_race_blocks_only_that_job_instead_of_reusing_an_unchecked_report(synthetic_api, monkeypatch):
    from dataclasses import replace
    from app.application.match_inputs.readiness import GetMatchInputReadinessUseCase
    client, factory, ids = synthetic_api
    _source(client, ids)
    original = GetMatchInputReadinessUseCase.execute
    def racing_readiness(self, job_id):
        ready = original(self, job_id)
        if job_id == ids[0]:
            return replace(ready, career_context=replace(ready.career_context, profile_version=999))
        return ready
    monkeypatch.setattr(GetMatchInputReadinessUseCase, 'execute', racing_readiness)
    before = _dump(factory)
    data = client.get('/api/v1/career-agent/runs/update_source/update-plan?scope=batch').json()
    assert data['items'][0]['status'] == 'input_blocked'
    assert data['items'][0]['blockerCodes'] == ['update_inputs_changed']
    assert data['reusableJobIds'] == ids[1:8]
    assert _dump(factory) == before


def test_missing_confirmed_evidence_has_a_profile_repair_instead_of_false_ready(synthetic_api):
    client, factory, ids = synthetic_api
    _source(client, ids)
    response = client.put('/api/v1/profile', json=dict(expectedVersion=1,
        headline='Synthetic partial confirmed profile', yearsOfExperience=5, evidence=[], skills=[]))
    assert response.status_code == 200, response.text
    before = _dump(factory)
    data = client.get('/api/v1/career-agent/runs/update_source/update-plan').json()
    assert not data['nextJobIds']
    assert all(i['status'] == 'input_blocked' and 'profile_evidence_missing' in i['blockerCodes']
        and i['repairHref'] == '/profile' for i in data['items'])
    assert _dump(factory) == before


def test_missing_database_schema_returns_repairable_503_without_sql_or_private_fact_leaks(synthetic_api):
    from sqlalchemy import text
    client, factory, ids = synthetic_api
    _source(client, ids)
    with factory.begin() as session:
        session.execute(text('DROP TABLE match_reports'))  # Disposable fixture schema only.
    response = client.get('/api/v1/career-agent/runs/update_source/update-plan')
    assert response.status_code == 503, response.text
    assert response.json()['error']['code'] == 'career_agent_storage_not_ready'
    assert '副本验证迁移' in response.json()['error']['message']
    assert 'SELECT' not in response.text and 'sqlite3' not in response.text
