"""New scoped runs from existing reports; real HTTP/SQLite, no paid matcher."""
import json
from pathlib import Path
from unittest.mock import Mock
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from app.agent.graph.hitl_service import CareerAgentHitlService
from app.agent.graph.checkpoint_port import CheckpointPersistenceError
from app.repositories.sqlalchemy_career_agent_checkpoint import SqlAlchemyCareerAgentCheckpointStore as Store
from app.workflows.semantic_match import SemanticMatchWorkflow
from .test_career_agent_analysis_snapshot import synthetic_api, approve
from .test_analysis_update_plan import _source, _profile, _dump


def _command(client, *, scope='targets', thread='updated'):
    plan = client.get(f'/api/v1/career-agent/runs/update_source/update-plan?scope={scope}').json()
    return dict(threadId=thread, runId=f'run_{thread}', requestId=f'req_{thread}',
        sourceResultId=plan['sourceResultId'], scope=scope, inputDigest=plan['inputDigest'], topN=2)


def _update(client, body):
    return client.post('/api/v1/career-agent/runs/update_source/updates', json=body)


def test_compatible_update_creates_real_new_analysis_and_retains_original(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    original = _source(client, ids)
    forbidden = Mock(side_effect=AssertionError('updating reports must not execute Match'))
    monkeypatch.setattr(SemanticMatchWorkflow, 'execute', forbidden)
    body = _command(client, scope='batch')
    response = _update(client, body)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['status'] == 'interrupted' and state['requestedJobIds'] == ids[:8]
    assert state['updateSourceThreadId'] == 'update_source' and state['updateSourceResultId'] == original['resultId']
    assert state['updateScope'] == 'batch'
    assert approve(client, state).json()['status'] == 'completed'
    saved = client.get('/api/v1/career-agent/runs/updated/result').json()
    assert saved['resultId'] != original['resultId'] and saved['threadId'] == 'updated'
    assert saved['profileVersion'] == original['profileVersion']
    assert client.get('/api/v1/career-agent/runs/update_source/result').json() == original
    before = _dump(factory)
    replay = _update(client, body)
    assert replay.status_code == 200 and replay.json()['status'] == 'completed'
    assert _dump(factory) == before
    conflict = _update(client, {**body, 'topN': 3})
    assert conflict.status_code == 409
    assert _dump(factory) == before
    forbidden.assert_not_called()


def test_changed_facts_need_fresh_preflight_and_recomputed_reports(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    _source(client, ids)
    old = _command(client)
    _profile(client)
    before = _dump(factory)
    assert _update(client, old).status_code == 409
    assert '事实已变化' in _update(client, old).json()['error']['message']
    assert _dump(factory) == before
    # Current implementation performs the actual pinned zero-model recomputation.
    state = _update(client, _command(client)).json()
    assert state['status'] == 'interrupted'
    assert all(s['status'] == 'completed' and s['attempt'] == 1 for s in state['updateSteps'])
    assert approve(client, state).json()['status'] == 'completed'
    saved = client.get('/api/v1/career-agent/runs/updated/result').json()
    assert saved['profileVersion'] == 2
    assert client.get('/api/v1/career-agent/runs/update_source/result').json()['profileVersion'] == 1


def test_accept_saved_then_process_restart_requires_explicit_continue(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    _source(client, ids)
    body = _command(client)
    real_continue = CareerAgentHitlService.continue_run
    monkeypatch.setattr(CareerAgentHitlService, 'continue_run', lambda *a, **k: (_ for _ in ()).throw(CheckpointPersistenceError('simulated crash')))
    response = _update(client, body)
    assert response.status_code == 503
    saved = Store(factory).load(thread_id='updated')  # New store instance, not an in-memory receipt.
    assert saved.current_step == 'analysis_created'
    monkeypatch.setattr(CareerAgentHitlService, 'continue_run', real_continue)
    before = _dump(factory)
    assert _update(client, body).json()['status'] == 'created'
    assert client.get('/api/v1/career-agent/runs/updated').json()['status'] == 'created'
    assert _dump(factory) == before
    response = client.post('/api/v1/career-agent/runs/updated/continue', json=dict(actionId='continue', expectedRevision=0))
    assert response.status_code == 200 and response.json()['status'] == 'interrupted'


def test_profile_changed_after_acceptance_cannot_resume_old_update(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    _source(client, ids)
    real_continue = CareerAgentHitlService.continue_run
    monkeypatch.setattr(CareerAgentHitlService, 'continue_run', lambda self, thread_id, **kwargs: self.get_state(thread_id=thread_id))
    assert _update(client, _command(client)).json()['status'] == 'created'
    monkeypatch.setattr(CareerAgentHitlService, 'continue_run', real_continue)
    _profile(client)
    response = client.post('/api/v1/career-agent/runs/updated/continue')
    assert response.json()['status'] == 'stale'
    assert client.get('/api/v1/career-agent/runs/updated/result').status_code == 404


def test_event_failure_rolls_back_run_acceptance(synthetic_api):
    client, factory, ids = synthetic_api
    _source(client, ids)
    body = _command(client)
    with factory.begin() as s:
        s.execute(text("CREATE TRIGGER stop_update BEFORE INSERT ON career_agent_run_events WHEN NEW.thread_id = 'updated' BEGIN SELECT RAISE(ABORT, 'test fault'); END"))
    before = _dump(factory)
    response = _update(client, body)
    assert response.status_code == 503 and response.json()['error']['retryable']
    assert 'test fault' not in response.text
    assert client.get('/api/v1/career-agent/runs/updated').status_code == 404
    assert _dump(factory) == before


def test_same_identity_concurrent_updates_accept_one_run(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    _source(client, ids)
    body = _command(client)
    # Freeze after durable acceptance, so this tests the real SQLite insert race, not the execution lease.
    monkeypatch.setattr(CareerAgentHitlService, 'continue_run', lambda self, thread_id, **kwargs: self.get_state(thread_id=thread_id))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: _update(client, body), range(2)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    store = Store(factory)
    assert len(store.load_history(thread_id='updated')) == 1
    assert store.load(thread_id='updated').revision == 0


def test_schema_and_invalid_requests(synthetic_api):
    from app.api.v1.schemas.analysis_update import StartAnalysisUpdateRequest
    client, factory, ids = synthetic_api
    _source(client, ids)
    body = _command(client)
    for changes in ({'scope': 'all'}, {'inputDigest': 'wrong'}, {'topN': 6}, {'providerBudget': 1}):
        assert _update(client, {**body, **changes}).status_code == 422
    schema = json.loads((Path(__file__).parents[3] / 'packages/contracts/schemas/analysis-update-start.schema.json').read_text())
    del schema['$schema'], schema['$id']
    assert schema == StartAnalysisUpdateRequest.model_json_schema(by_alias=True)


def test_new_report_after_acceptance_marks_old_preflight_stale(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    _source(client, ids)
    real_continue = CareerAgentHitlService.continue_run
    monkeypatch.setattr(CareerAgentHitlService, 'continue_run', lambda self, thread_id, **kwargs: self.get_state(thread_id=thread_id))
    assert _update(client, _command(client)).json()['status'] == 'created'
    # Same Profile version but a different report identity is still a different fixed input set.
    assert client.post(f'/api/v1/jobs/{ids[0]}/match-report').status_code == 200
    monkeypatch.setattr(CareerAgentHitlService, 'continue_run', real_continue)
    state = client.post('/api/v1/career-agent/runs/updated/continue', json=dict(actionId='explicit', expectedRevision=0)).json()
    assert state['status'] == 'stale' and state['currentStep'] == 'update_inputs_changed'
    assert client.get('/api/v1/career-agent/runs/updated/result').status_code == 404


def test_update_origin_and_report_binding_are_immutable(synthetic_api):
    from app.agent.graph.checkpoint_port import CheckpointConflictError, next_revision
    import pytest
    client, factory, ids = synthetic_api
    _source(client, ids)
    assert _update(client, _command(client)).status_code == 200
    state = Store(factory).load(thread_id='updated')
    for changes in (dict(update_source_thread_id='other'), dict(update_source_result_id='other'),
                    dict(update_scope='batch'), dict(update_input_digest='b' * 64), dict(update_report_ids=())):
        with pytest.raises(CheckpointConflictError):
            next_revision(state, replace(state, **changes))
