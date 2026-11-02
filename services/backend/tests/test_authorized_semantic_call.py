"""Actual workflow + file SQLite + bounded HTTP transport. No live provider."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import httpx
import pytest
from sqlalchemy import text
from app.api import deps
from app.core.config import Settings
import app.llm.authorized_semantic_factory as module
from .test_first_job_journey import first_user, save_inputs, prepare_job


@pytest.fixture
def authorized_match(first_user, monkeypatch):
    client, factory = first_user
    save_inputs(client)
    changed = client.put('/api/v1/profile', json={"expectedVersion": 1, "headline": "合成后端工程师", "yearsOfExperience": 2,
        "evidence": [{"key": "python", "type": "project", "summary": "使用 Python 开发并维护服务", "source": "合成验收"}], "skills": []})
    assert changed.status_code == 200
    job = prepare_job(client, "任职要求：熟练掌握 Python，并能够以真实项目经历说明 Python 的工程应用、开发与维护能力。")
    configured = Settings(_env_file=None, semantic_match_provider='openai', semantic_match_model='test-only',
        requirement_extractor_provider='fixture', openai_api_key='never-live', openai_base_url='https://example.test/v1')
    monkeypatch.setattr(deps, 'get_settings', lambda: configured)
    calls = []
    def ok(request):
        body = json.loads(request.content)
        assert body['max_output_tokens'] == 4096
        assert request.extensions['timeout']['read'] == 60
        data = json.loads(body['input'][1]['content'][0]['text'])
        result = {'assessments': [{'requirementId': r['requirementId'], 'verdict': 'partial',
            'evidenceIds': [r['candidates'][0]['evidenceId']], 'reason': '存在相关经历，仍需核实完整能力。'} for r in data['requirements']]}
        return httpx.Response(200, json={'output': [{'type': 'message', 'content': [{'type':'output_text', 'text': json.dumps(result)}]}],
            'usage': {'input_tokens': 90, 'output_tokens': 35}})
    state = {'handler': ok}
    original = module.authorized_semantic_factory
    def handler(request):
        calls.append(request)
        return state['handler'](request)
    monkeypatch.setattr(module, 'authorized_semantic_factory', lambda settings, journal:
        original(settings, journal, lambda: httpx.MockTransport(handler)))
    return client, factory, job, calls, state, ok


def payload(client, job, action='match-one'):
    response = client.get(f'/api/v1/jobs/{job}/semantic-call-plan')
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan['available'], plan
    assert plan['requirements'][0]['candidates']
    return {'actionId': action, 'planDigest': plan['planDigest'], 'confirmed': True, 'maxProviderCalls': 1}


def test_success_replay_and_conflict(authorized_match):
    c, f, job, calls, _, _ = authorized_match
    path = f'/api/v1/jobs/{job}'
    command = payload(c, job)
    result = c.post(path+'/semantic-calls', json=command)
    assert result.status_code == 200, result.text
    record = result.json()
    assert record['status'] == 'completed', record
    assert record['reportId'] and record['attempts'] == 1
    assert (record['inputTokens'], record['outputTokens']) == (90, 35)
    history = c.get(path+'/match-reports').json()
    assert history['count'] == 1 and history['items'][0]['isCurrent']
    assert history['items'][0]['report']['providerCalls'] == 1
    assert history['items'][0]['report']['evidenceLinks']
    assert c.post(path+'/semantic-calls', json=command).json() == record
    assert c.get(path+'/semantic-calls/match-one').json() == record
    assert c.post(path+'/semantic-calls', json={**command, 'confirmed':False}).status_code == 409
    assert len(calls) == 1
    assert 'never-live' not in json.dumps(record)


@pytest.mark.parametrize('change', [{'confirmed':False}, {'maxProviderCalls':0}])
def test_no_consent_zero_calls(authorized_match, change):
    c, _, job, calls, _, _ = authorized_match
    command = payload(c, job)
    assert c.post(f'/api/v1/jobs/{job}/semantic-calls', json={**command, **change}).status_code == 409
    assert calls == []


def test_legacy_route_stays_zero_budget(authorized_match):
    c, _, job, calls, _, _ = authorized_match
    assert c.post(f'/api/v1/jobs/{job}/match-report').status_code != 200
    assert calls == []


def test_timeout_no_auto_retry(authorized_match):
    c, f, job, calls, state, _ = authorized_match
    def timeout(request):
        raise httpx.ReadTimeout('private evidence must not be returned')
    state['handler'] = timeout
    command = payload(c, job)
    path = f'/api/v1/jobs/{job}/semantic-calls'
    r = c.post(path, json=command).json()
    assert r['status'] == 'uncertain' and r['attempts'] == 1, r
    assert r['inputTokens'] is None and 'private' not in json.dumps(r)
    assert c.post(path, json=command).json() == r
    assert c.post(path, json=payload(c, job, 'new')).status_code == 409
    assert len(calls) == 1


def test_profile_changes_during_http_no_report(authorized_match):
    c, f, job, calls, state, ok = authorized_match
    def mutate(request):
        old = c.get('/api/v1/profile').json()
        assert c.put('/api/v1/profile', json={'expectedVersion':2, 'headline':'新增已确认事实',
            'yearsOfExperience':2, 'evidence':[{'key':'new', 'type':'project','summary':'新的合成经历','source':'合成'}], 'skills':[]}).status_code == 200
        return ok(request)
    state['handler'] = mutate
    r = c.post(f'/api/v1/jobs/{job}/semantic-calls', json=payload(c, job)).json()
    assert r['status'] == 'failed' and r['errorCode'] == 'match_facts_changed', r
    assert r['attempts'] == 1 and r['inputTokens'] == 90
    assert c.get(f'/api/v1/jobs/{job}/match-reports').json()['count'] == 0


def test_report_and_completion_atomic(authorized_match):
    c, f, job, calls, _, _ = authorized_match
    with f.begin() as s:
        s.execute(text("CREATE TRIGGER break_finish BEFORE UPDATE OF status ON semantic_calls WHEN NEW.status='completed' BEGIN SELECT RAISE(ABORT, 'test'); END"))
    r = c.post(f'/api/v1/jobs/{job}/semantic-calls', json=payload(c, job)).json()
    assert r['status'] == 'failed' and r['reportId'] is None, r
    assert r['attempts'] == 1 and r['outputTokens'] == 35
    assert c.get(f'/api/v1/jobs/{job}/match-reports').json()['count'] == 0


def test_two_tabs_only_one_call(authorized_match):
    c, f, job, calls, state, ok = authorized_match
    entered, release = Event(), Event()
    def wait(request):
        entered.set()
        assert release.wait(10)
        return ok(request)
    state['handler'] = wait
    command = payload(c, job)
    path = f'/api/v1/jobs/{job}/semantic-calls'
    with ThreadPoolExecutor(2) as pool:
        future = pool.submit(c.post, path, json=command)
        assert entered.wait(10)
        try:
            assert c.post(path, json=command).json()['status'] == 'running'
            assert c.post(path, json={**command, 'actionId':'second-tab'}).status_code == 409
        finally:
            release.set()
        assert future.result().json()['status'] == 'completed'
    assert len(calls) == 1


def test_changed_plan_rejected_before_dispatch(authorized_match):
    c, f, job, calls, _, _ = authorized_match
    command = payload(c, job)
    with f.begin() as s:
        s.execute(text('UPDATE jobs SET description=description || :d WHERE id=:id'), {'d':' 新的岗位条件', 'id':job})
    r = c.post(f'/api/v1/jobs/{job}/semantic-calls', json=command)
    assert r.status_code == 409 and calls == []


@pytest.mark.parametrize('status', [429, 503, 307])
def test_no_retry_or_redirect(authorized_match, status):
    c, f, job, calls, state, _ = authorized_match
    state['handler'] = lambda request: httpx.Response(status, headers={'Location':'https://example.test/other'}, json={})
    r = c.post(f'/api/v1/jobs/{job}/semantic-calls', json=payload(c, job)).json()
    assert r['status'] == 'failed' and r['attempts'] == 1 and r['responseStatus'] == status
    assert len(calls) == 1


def test_expired_executor_cannot_overwrite_new_result(authorized_match):
    c, f, job, calls, state, ok = authorized_match
    entered, release = Event(), Event()
    def old(request):
        entered.set()
        assert release.wait(10)
        return ok(request)
    state['handler'] = old
    command = payload(c, job)
    path = f'/api/v1/jobs/{job}/semantic-calls'
    with ThreadPoolExecutor(2) as pool:
        future = pool.submit(c.post, path, json=command)
        assert entered.wait(10)
        try:
            with f.begin() as s:
                s.execute(text("UPDATE semantic_calls SET created_at=datetime('now','-5 minutes') WHERE action_id='match-one'"))
            assert c.get(path+'/match-one').json()['status'] == 'uncertain'
            state['handler'] = ok
            new = {**payload(c, job, 'replacement'), 'acknowledgedPriorRequestId':'match-one'}
            saved = c.post(path, json=new).json()
            assert saved['status'] == 'completed', saved
        finally:
            release.set()
        assert future.result().json()['status'] == 'uncertain'
    assert c.get(f'/api/v1/jobs/{job}/match-reports').json()['count'] == 1
    assert len(calls) == 2


def test_shared_contracts_are_current():
    from pathlib import Path
    from app.api.v1.schemas.semantic_calls import SemanticCallCommand, SemanticCallPlan, SemanticCallRecord
    for suffix, model in [('command',SemanticCallCommand),('plan',SemanticCallPlan),('record',SemanticCallRecord)]:
        schema = Path(__file__).resolve().parents[3]/'packages/contracts/schemas'/f'semantic-call-{suffix}.schema.json'
        assert json.loads(schema.read_text()) == model.model_json_schema(by_alias=True)


def test_invalid_evidence_cannot_be_saved(authorized_match):
    c, f, job, calls, state, ok = authorized_match
    def invent(request):
        response = ok(request)
        body = response.json()
        output = json.loads(body['output'][0]['content'][0]['text'])
        output['assessments'][0]['evidenceIds'] = ['invented-evidence']
        body['output'][0]['content'][0]['text'] = json.dumps(output)
        return httpx.Response(200, json=body)
    state['handler'] = invent
    r = c.post(f'/api/v1/jobs/{job}/semantic-calls', json=payload(c, job)).json()
    assert r['status'] == 'failed' and r['attempts'] == 1 and r['outputTokens'] == 35
    assert c.get(f'/api/v1/jobs/{job}/match-reports').json()['count'] == 0


def test_plan_is_read_only_and_missing_job_is_clear(authorized_match):
    c, f, job, calls, _, _ = authorized_match
    payload(c, job)
    with f() as s:
        assert s.execute(text('SELECT count(*) FROM semantic_calls')).scalar_one() == 0
    assert calls == []
    assert c.get('/api/v1/jobs/nonexistent/semantic-call-plan').status_code == 404


def test_recall_version_change_invalidates_prior_authorization(authorized_match, monkeypatch):
    c, _, job, calls, _, _ = authorized_match
    command = payload(c, job)
    monkeypatch.setattr('app.application.semantic_match.authorized.RETRIEVAL_VERSION', 'next-recall-rule')
    response = c.post(f'/api/v1/jobs/{job}/semantic-calls', json=command)
    assert response.status_code == 409 and calls == []


def test_candidate_summary_change_invalidates_authorization_even_without_version_bump(authorized_match):
    c, factory, job, calls, _, _ = authorized_match
    command = payload(c, job)
    with factory.begin() as session:
        session.execute(text("UPDATE profile_evidence SET summary=summary || ' 新的具体事实'"))
    response = c.post(f'/api/v1/jobs/{job}/semantic-calls', json=command)
    assert response.status_code == 409 and calls == []


def test_oversized_actual_model_payload_blocks_without_truncation_or_dispatch(authorized_match):
    c, factory, job, calls, _, _ = authorized_match
    with factory.begin() as session:
        session.execute(text("UPDATE profile_evidence SET summary=:s"), {'s': 'Python 的真实工程经历。' * 1500})
    plan = c.get(f'/api/v1/jobs/{job}/semantic-call-plan').json()
    assert plan['blockerCode'] == 'semantic_input_outside_call_limit' and not plan['available']
    assert len(plan['requirements'][0]['candidates'][0]['summary']) > 12000
    response = c.post(f'/api/v1/jobs/{job}/semantic-calls', json={
        'actionId':'oversize', 'planDigest':plan['planDigest'], 'confirmed':True, 'maxProviderCalls':1})
    assert response.status_code == 409 and calls == []
