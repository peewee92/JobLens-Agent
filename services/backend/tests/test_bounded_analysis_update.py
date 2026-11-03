"""Real HTTP + SQLite steps, failures, fixed inputs and competing execution leases."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from unittest.mock import Mock
import json
from pathlib import Path

import pytest
from sqlalchemy import select, func, text
from app.api import deps
from app.db.models import MatchReportORM
from app.application.rule_match import BuildPinnedRuleMatch, _NoModel
from app.repositories.sqlalchemy_career_agent_checkpoint import SqlAlchemyCareerAgentCheckpointStore as Store
from .test_career_agent_analysis_snapshot import synthetic_api, approve
from .test_analysis_update_plan import _source, _profile, _dump
from .test_analysis_update_start import _command, _update


def _continue(client, state, action='next', partial=False):
    return client.post(f"/api/v1/career-agent/runs/{state['threadId']}/continue", json=dict(
        actionId=action, expectedRevision=state['revision'], useCompletedOnly=partial))


def _count(factory):
    with factory() as s:
        return s.scalar(select(func.count()).select_from(MatchReportORM))


def _begin(client, ids):
    _source(client, ids)
    _profile(client)
    body = _command(client, scope='batch')
    response = _update(client, body)
    assert response.status_code == 200, response.text
    return response.json(), body


def test_eight_jobs_execute_five_then_three_with_replay_safe_commands(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    forbidden = Mock(side_effect=AssertionError('paid provider must never run'))
    monkeypatch.setattr(_NoModel, 'match', forbidden)
    state, body = _begin(client, ids)
    assert state['status'] == 'running' and state['currentStep'] == 'update_matching'
    assert [s['status'] for s in state['updateSteps']] == ['completed']*5 + ['pending']*3
    assert _count(factory) == 25
    before = _dump(factory)
    assert _update(client, body).json() == state
    assert client.get('/api/v1/career-agent/runs/updated').json() == state
    assert Store(factory).load(thread_id='updated').update_steps[0].report_id == state['updateSteps'][0]['reportId']
    assert _dump(factory) == before
    missing = client.post('/api/v1/career-agent/runs/updated/continue')
    assert missing.status_code == 409 and _dump(factory) == before
    response = _continue(client, state)
    assert response.status_code == 200, response.text
    done = response.json()
    assert done['status'] == 'interrupted' and _count(factory) == 28
    assert all(s['status'] == 'completed' and s['attempt'] == 1 for s in done['updateSteps'])
    before = _dump(factory)
    assert _continue(client, state).json() == done  # Old expectedRevision is legal only for exact replay.
    assert _continue(client, state, partial=True).status_code == 409
    assert _dump(factory) == before
    assert approve(client, done).json()['status'] == 'completed'
    result = client.get('/api/v1/career-agent/runs/updated/result').json()
    assert result['profileVersion'] == 2 and len(result['bindings']) == 8 and not result['updatePartial']
    assert client.get('/api/v1/career-agent/runs/update_source/result').json()['profileVersion'] == 1
    forbidden.assert_not_called()


def test_single_compute_failure_keeps_other_reports_and_retry_does_not_starve_pending(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    actual = BuildPinnedRuleMatch.execute
    def fail_one(self, **facts):
        if facts['job'].id == ids[0]: raise RuntimeError('private computation detail')
        return actual(self, **facts)
    monkeypatch.setattr(BuildPinnedRuleMatch, 'execute', fail_one)
    state, body = _begin(client, ids)
    assert state['updateSteps'][0]['status'] == 'failed' and _count(factory) == 24
    assert 'private computation detail' not in json.dumps(state)
    assert any(s.last_error_class == 'RuntimeError' for s in Store(factory).load_history(thread_id='updated'))
    monkeypatch.setattr(BuildPinnedRuleMatch, 'execute', actual)
    response = _continue(client, state)
    assert response.status_code == 200, response.text
    done = response.json()
    assert done['status'] == 'interrupted' and _count(factory) == 28
    assert done['updateSteps'][0]['attempt'] == 2
    assert all(s['attempt'] == 1 for s in done['updateSteps'][1:])


def test_user_can_explicitly_finish_partial_without_hiding_unanalysed_scope(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    actual = BuildPinnedRuleMatch.execute
    def fail_one(self, **facts):
        if facts['job'].id == ids[0]: raise RuntimeError('test fault')
        return actual(self, **facts)
    monkeypatch.setattr(BuildPinnedRuleMatch, 'execute', fail_one)
    state, body = _begin(client, ids)
    before = _count(factory)
    response = _continue(client, state, partial=True)
    assert response.status_code == 200, response.text
    partial = response.json()
    assert partial['status'] == 'interrupted' and partial['updatePartial']
    assert partial['requestedJobIds'] == ids[:8] and partial['rankedJobIds'] == ids[1:5]
    assert _count(factory) == before
    assert approve(client, partial).json()['status'] == 'completed'
    result = client.get('/api/v1/career-agent/runs/updated/result').json()
    assert result['updatePartial'] and set(result['unanalysedJobIds']) == {ids[0], *ids[5:8]}
    assert {b['jobId'] for b in result['bindings']} == set(ids[1:5])


def test_report_insert_failure_rolls_back_step_completion_but_retains_earlier_success(synthetic_api):
    client, factory, ids = synthetic_api
    _source(client, ids); _profile(client)
    with factory.begin() as s:
        s.execute(text("CREATE TRIGGER fail_report BEFORE INSERT ON match_reports WHEN NEW.job_id = 'job_mcp_demo_03' BEGIN SELECT RAISE(ABORT, 'private SQL fault'); END"))
    body = _command(client, scope='batch')
    response = _update(client, body)
    assert response.status_code == 503 and 'private SQL fault' not in response.text
    state = client.get('/api/v1/career-agent/runs/updated').json()
    assert [s['status'] for s in state['updateSteps'][:3]] == ['completed', 'completed', 'running']
    assert _count(factory) == 22
    before = _dump(factory)
    assert _update(client, body).json() == state and _dump(factory) == before
    with factory.begin() as s: s.execute(text('DROP TRIGGER fail_report'))
    continued = _continue(client, state).json()
    assert [s['status'] for s in continued['updateSteps']] == ['completed']*7 + ['pending']
    assert continued['updateSteps'][2]['attempt'] == 2 and _count(factory) == 27
    done = _continue(client, continued, action='last').json()
    assert done['status'] == 'interrupted' and _count(factory) == 28


def test_facts_change_during_compute_prevents_report_and_completion_commit(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    actual = BuildPinnedRuleMatch.execute
    def racing(self, **facts):
        report = actual(self, **facts)
        result = client.put('/api/v1/profile', json=dict(expectedVersion=2, headline='Synthetic newer fact',
            yearsOfExperience=6, evidence=[dict(key='p', type='project', summary='Python outcome', source='test')],
            skills=[dict(name='Python', level='strong', evidenceKeys=['p'])]))
        assert result.status_code == 200, result.text
        return report
    monkeypatch.setattr(BuildPinnedRuleMatch, 'execute', racing)
    state, body = _begin(client, ids)
    assert state['status'] == 'stale' and state['currentStep'] == 'update_inputs_changed'
    assert state['updateSteps'][0]['status'] == 'running' and state['updateSteps'][0]['reportId'] is None
    assert _count(factory) == 20
    assert client.get('/api/v1/career-agent/runs/updated/result').status_code == 404


def test_expired_old_executor_cannot_overwrite_new_executor_results(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    _source(client, ids); _profile(client)
    now = [100.0]
    class ClockStore(Store):
        def __init__(self, factory, **kwargs): super().__init__(factory, clock=lambda: now[0], **kwargs)
    monkeypatch.setattr(deps, 'SqlAlchemyCareerAgentCheckpointStore', ClockStore)
    started, release, lock = Event(), Event(), Lock()
    first = [True]
    actual = BuildPinnedRuleMatch.execute
    def delayed(self, **facts):
        with lock:
            slow = first[0]; first[0] = False
        if slow:
            started.set()
            assert release.wait(30), 'test release timeout'
        return actual(self, **facts)
    monkeypatch.setattr(BuildPinnedRuleMatch, 'execute', delayed)
    body = _command(client, scope='batch')
    with ThreadPoolExecutor(max_workers=1) as pool:
        old = pool.submit(_update, client, body)
        try:
            assert started.wait(15)
            claimed = client.get('/api/v1/career-agent/runs/updated').json()
            assert claimed['updateSteps'][0]['status'] == 'running'
            now[0] += 121  # Expire the real DB lease, without sleeping.
            newer = _continue(client, claimed, action='takeover')
            assert newer.status_code == 200, newer.text
            current = newer.json()
            assert [s['status'] for s in current['updateSteps']] == ['completed']*5 + ['pending']*3
            assert current['updateSteps'][0]['attempt'] == 2
        finally:
            release.set()
        assert old.result(timeout=15).status_code == 409
    assert client.get('/api/v1/career-agent/runs/updated').json() == current
    assert _count(factory) == 25  # No late duplicate report from the obsolete executor.


def test_model_required_stays_waiting_with_zero_calls_and_no_fake_partial_success(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    _source(client, ids); _profile(client, semantic=True)
    forbidden = Mock(side_effect=AssertionError('no rule/model execution authorized for semantic work'))
    monkeypatch.setattr(BuildPinnedRuleMatch, 'execute', forbidden)
    response = _update(client, _command(client, scope='batch'))
    assert response.status_code == 200, response.text
    state = response.json()
    assert all(s['status'] == 'requires_model' and s['attempt'] == 0 for s in state['updateSteps'])
    assert state['status'] == 'running' and _count(factory) == 20
    assert _continue(client, state, partial=True).status_code == 409
    assert client.get('/api/v1/career-agent/runs/updated/result').status_code == 404
    forbidden.assert_not_called()


def test_continue_contract_matches_shared_schema():
    from app.api.v1.schemas.career_agent import ContinueAnalysisRequest
    schema = json.loads((Path(__file__).parents[3]/'packages/contracts/schemas/career-agent-continue-request.schema.json').read_text())
    del schema['$schema'], schema['$id']
    assert schema == ContinueAnalysisRequest.model_json_schema(by_alias=True)


def test_raw_transition_cannot_claim_completion_without_atomic_report_write(synthetic_api):
    from dataclasses import replace
    from app.agent.graph.checkpoint_port import CheckpointConflictError
    client, factory, ids = synthetic_api
    state, body = _begin(client, ids)
    store = Store(factory)
    current = store.load(thread_id='updated')
    step = current.update_steps[5]
    claimed = replace(step, status='running', attempt=1)
    # Claim is a legitimate runtime write; completion without a report transaction is not.
    current = store.transition(current, replace(current,
        update_steps=tuple(claimed if s.job_id == step.job_id else s for s in current.update_steps)))
    fake = replace(claimed, status='completed', report_id='invented_report')
    with pytest.raises(CheckpointConflictError):
        store.transition(current, replace(current,
            update_steps=tuple(fake if s.job_id == step.job_id else s for s in current.update_steps)))
    assert store.load(thread_id='updated') == current and _count(factory) == 25
