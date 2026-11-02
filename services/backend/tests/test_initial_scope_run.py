"""Fresh scopes reuse the durable run and its atomic, zero-model match execution."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from sqlalchemy import delete, func, select, text
from app.application.rule_match import _NoModel
from app.db.models import MatchReportORM
from .test_career_agent_analysis_snapshot import synthetic_api


def _prepare(client, factory, ids):
    job = ids[0]
    with factory.begin() as session:
        session.execute(delete(MatchReportORM).where(MatchReportORM.job_id == job))
    plan = client.post('/api/v1/career-agent/initial-scope-plan', json={'jobIds': [job]})
    assert plan.status_code == 200, plan.text
    body = {'threadId': 'fresh-thread', 'runId': 'fresh-run', 'requestId': 'fresh-request',
            'jobIds': [job], 'inputDigest': plan.json()['inputDigest'], 'topN': 1}
    return job, plan.json(), body


def _count(factory, job):
    with factory() as session:
        return session.scalar(select(func.count()).select_from(MatchReportORM).where(MatchReportORM.job_id == job))


def test_fresh_scope_uses_existing_durable_execution_and_replay(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    job, plan, body = _prepare(client, factory, ids)
    assert plan['items'][0]['status'] == 'ready'
    forbidden = Mock(side_effect=AssertionError('no model'))
    monkeypatch.setattr(_NoModel, 'match', forbidden)
    response = client.post('/api/v1/career-agent/initial-scope-runs', json=body)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['status'] == 'interrupted' and state['updateSteps'][0]['status'] == 'completed'
    assert state['updateSourceThreadId'] is None and _count(factory, job) == 1
    assert client.post('/api/v1/career-agent/initial-scope-runs', json=body).json() == state
    assert client.post('/api/v1/career-agent/initial-scope-runs', json={**body, 'topN': 2}).status_code == 409
    assert _count(factory, job) == 1
    forbidden.assert_not_called()


def test_concurrent_replay_and_failed_report_save_are_recoverable(synthetic_api):
    client, factory, ids = synthetic_api
    job, _, body = _prepare(client, factory, ids)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post('/api/v1/career-agent/initial-scope-runs', json=body), range(2)))
    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
    assert _count(factory, job) == 1

    job2 = ids[1]
    with factory.begin() as session:
        session.execute(delete(MatchReportORM).where(MatchReportORM.job_id == job2))
        session.execute(text("CREATE TRIGGER fail_fresh_report BEFORE INSERT ON match_reports BEGIN SELECT RAISE(ABORT, 'private failure'); END"))
    plan = client.post('/api/v1/career-agent/initial-scope-plan', json={'jobIds': [job2]}).json()
    other = {**body, 'threadId': 'fresh-other', 'runId': 'run-other', 'requestId': 'req-other', 'jobIds': [job2], 'inputDigest': plan['inputDigest']}
    response = client.post('/api/v1/career-agent/initial-scope-runs', json=other)
    assert response.status_code == 503 and 'private failure' not in response.text
    state = client.get('/api/v1/career-agent/runs/fresh-other').json()
    assert state['updateSteps'][0]['status'] == 'running' and _count(factory, job2) == 0
    with factory.begin() as session:
        session.execute(text('DROP TRIGGER fail_fresh_report'))
    resumed = client.post('/api/v1/career-agent/runs/fresh-other/continue', json={
        'actionId': 'retry-after-save-failure', 'expectedRevision': state['revision']})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['status'] == 'interrupted' and _count(factory, job2) == 1


def test_fresh_scope_does_not_start_when_preflight_is_stale(synthetic_api):
    client, factory, ids = synthetic_api
    job, _, body = _prepare(client, factory, ids)
    job_detail = client.get(f'/api/v1/jobs/{job}').json()
    marked = client.put(f'/api/v1/jobs/{job}/user-availability', json={
        'userMarkedInactive': True, 'expectedRevision': job_detail['availabilityRevision']})
    assert marked.status_code == 200
    assert client.post('/api/v1/career-agent/initial-scope-runs', json=body).status_code == 409
    assert client.get('/api/v1/career-agent/runs/fresh-thread').status_code == 404
    assert _count(factory, job) == 0


def test_fresh_scope_approve_saves_result_without_fabricated_history(synthetic_api):
    client, factory, ids = synthetic_api
    _, _, body = _prepare(client, factory, ids)
    state = client.post('/api/v1/career-agent/initial-scope-runs', json=body).json()
    result = client.post('/api/v1/career-agent/runs/fresh-thread/resume', json={
        'interruptId': state['interruptId'], 'actionId': 'approve-fresh', 'decision': 'approve'})
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'completed'
    saved = client.get('/api/v1/career-agent/runs/fresh-thread/result')
    assert saved.status_code == 200 and saved.json()['isCurrent']
    assert client.get('/api/v1/career-agent/runs/fresh-thread/comparison').status_code == 409


def test_distinct_concurrent_scope_commands_cannot_commit_two_reports(synthetic_api):
    client, factory, ids = synthetic_api
    job, _, first = _prepare(client, factory, ids)
    second = {**first, 'threadId': 'other-thread', 'runId': 'other-run', 'requestId': 'other-request'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda body: client.post('/api/v1/career-agent/initial-scope-runs', json=body), [first, second]))
    assert all(r.status_code in (200, 409) for r in responses), [r.text for r in responses]
    assert _count(factory, job) == 1
    assert any(r.status_code == 200 and r.json()['status'] == 'interrupted' for r in responses)


def test_unknown_semantics_stays_blocked_without_a_model_call(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    job, _, body = _prepare(client, factory, ids)
    profile = client.get('/api/v1/profile').json()
    response = client.put('/api/v1/profile', json={
        'expectedVersion': profile['version'], 'headline': 'Synthetic facts', 'yearsOfExperience': 5,
        'evidence': [{'key': 'actual', 'type': 'project', 'summary': 'Implemented a Python backend outcome', 'source': 'Synthetic test repository'}],
        'skills': [{'name': 'TypeScript', 'level': 'strong', 'evidenceKeys': ['actual']}]})
    assert response.status_code == 200, response.text
    plan = client.post('/api/v1/career-agent/initial-scope-plan', json={'jobIds': [job]}).json()
    assert plan['items'][0]['status'] == 'requires_model'
    forbidden = Mock(side_effect=AssertionError('no model'))
    monkeypatch.setattr(_NoModel, 'match', forbidden)
    response = client.post('/api/v1/career-agent/initial-scope-runs', json={**body, 'inputDigest': plan['inputDigest']})
    assert response.status_code == 200, response.text
    assert response.json()['updateSteps'][0]['status'] == 'requires_model'
    assert _count(factory, job) == 0
    forbidden.assert_not_called()


def test_initial_request_contracts_match_validation(synthetic_api):
    import json
    from pathlib import Path
    from jsonschema import Draft202012Validator
    client, factory, ids = synthetic_api
    _, _, body = _prepare(client, factory, ids)
    root = Path(__file__).resolve().parents[3] / 'packages/contracts/schemas'
    for name, payload in [('initial-scope-plan-request.schema.json', {'jobIds': [ids[0]]}),
                          ('initial-scope-start-request.schema.json', body)]:
        Draft202012Validator(json.loads((root / name).read_text())).validate(payload)
    assert client.post('/api/v1/career-agent/initial-scope-plan', json={'jobIds': ['']}).status_code == 422
    assert client.post('/api/v1/career-agent/initial-scope-plan', json={'jobIds': ids[:1], 'unexpected': True}).status_code == 422
