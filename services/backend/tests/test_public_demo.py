"""Public demo uses actual business handlers, with no private database or paid models."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.demo.public_app import create_public_app
from app.demo.sessions import DemoSessions, DemoError

SECRET = 'test-proxy-secret-' * 3
ORIGIN = 'https://joblens.example'


@pytest.fixture(scope='module')
def template(tmp_path_factory):
    root = Path(__file__).parents[3]
    spec = importlib.util.spec_from_file_location('launcher_for_public', root / 'scripts/demo.py')
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    directory = tmp_path_factory.mktemp('public-template')
    demo.prepare_demo(directory)
    return directory / 'demo.db'


@pytest.fixture
def setup(tmp_path, template):
    now = [100.0]
    manager = DemoSessions(tmp_path / 'sessions', template, clock=lambda: now[0])
    with TestClient(create_public_app(manager, secret=SECRET, origin=ORIGIN)) as client:
        yield client, manager, now
    manager.close()


def headers(token=None):
    return {'X-Joblens-Proxy': SECRET, 'Origin': ORIGIN, 'X-Demo-Client': 'test', **({'X-Demo-Session': token} if token else {})}


def create(client):
    response = client.post('/api/v1/demo/session', headers=headers())
    assert response.status_code == 200, response.text
    return response.json()['sessionToken']


def test_deny_by_default_and_no_model_or_upload(setup):
    c, _, _ = setup
    assert c.get('/api/v1/health').status_code == 200
    assert c.get('/api/v1/profile').status_code == 401
    token = create(c)
    for path in ('/api/v1/profile', '/api/v1/profile-proposals/file', '/api/v1/job-imports/manual',
                 '/api/v1/jobs/anything/requirement-calls', '/api/v1/semantic-calls', '/api/v1/career-agent/turn'):
        assert c.post(path, headers=headers(token), json={}).status_code == 403
    assert c.get('/docs', headers=headers(token)).status_code == 403
    bad = headers(token); bad['Origin'] = 'https://attacker.example'
    assert c.post('/api/v1/career-agent/runs', headers=bad, json={}).status_code == 403
    assert c.post('/api/v1/career-agent/runs', headers=headers(token), content=b'x' * 32769).status_code == 413
    assert c.get('/api/v1/readiness', headers=headers(token)).status_code == 200


def test_two_parallel_visitors_and_real_flow(setup, monkeypatch):
    c, manager, _ = setup
    # All runtime networking forbidden: fixtures were prepared before this guard.
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('public demo attempted network'))
    a, b = create(c), create(c)
    def get_jobs(token):
        r = c.get('/api/v1/jobs', headers=headers(token)); assert r.status_code == 200, r.text
        return r.json()['items']
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs_a, jobs_b = list(pool.map(get_jobs, (a, b)))
    assert len(jobs_a) == len(jobs_b) == 3
    payload = dict(threadId='visitor-a', runId='run-a', requestId='request-a', jobIds=[j['id'] for j in jobs_a], topN=3)
    start = c.post('/api/v1/career-agent/runs', headers=headers(a), json=payload)
    assert start.status_code == 200, start.text
    state = start.json(); assert state['status'] == 'interrupted', state
    assert c.get('/api/v1/career-agent/runs/visitor-a', headers=headers(b)).status_code == 404
    decision = dict(interruptId=state['interruptId'], actionId='choose', decision='approve')
    done = c.post('/api/v1/career-agent/runs/visitor-a/resume', headers=headers(a), json=decision)
    assert done.status_code == 200 and done.json()['status'] == 'completed', done.text
    result = c.get('/api/v1/career-agent/runs/visitor-a/result', headers=headers(a)).json()
    command = dict(commandId='execute', resultId=result['resultId'], jobIds=result['selectedJobIds'])
    path = '/api/v1/career-agent/runs/visitor-a/execution'
    receipt = c.post(path, headers=headers(a), json=command)
    assert receipt.status_code == 200, receipt.text
    assert c.post(path, headers=headers(a), json=command).json() == receipt.json()
    workspace = receipt.json()['items'][0]
    root = '/api/v1/application-workspaces/' + workspace['workspaceId']
    assert c.get(root, headers=headers(b)).status_code == 404
    action_path = root + '/actions/' + workspace['actionIds'][0] + '/status'
    action = c.post(action_path, headers=headers(a), json=dict(actorId='local-user', expectedStatus='todo', newStatus='in_progress'))
    assert action.status_code == 200, action.text
    assert c.get(root+'/actions', headers=headers(a)).json()[0]['status'] == 'in_progress'
    with manager.acquire(a) as context, context.sessions() as s:
        assert s.execute(text('SELECT count(*) FROM application_workspaces')).scalar_one() == 1
        assert s.execute(text('SELECT count(*) FROM requirement_calls')).scalar_one() == 0
        assert s.execute(text('SELECT count(*) FROM semantic_calls')).scalar_one() == 0
    with manager.acquire(b) as context, context.sessions() as s:
        assert s.execute(text('SELECT count(*) FROM application_workspaces')).scalar_one() == 0
        assert s.execute(text('SELECT count(*) FROM career_agent_runs')).scalar_one() == 0


def test_expiry_reset_and_restart(setup):
    c, manager, now = setup
    token = create(c)
    new = c.delete('/api/v1/demo/session', headers=headers(token))
    assert new.status_code == 200
    assert c.get('/api/v1/profile', headers=headers(token)).status_code == 410
    token = new.json()['sessionToken']
    now[0] += 1800
    assert c.get('/api/v1/profile', headers=headers(token)).status_code == 410
    token = create(c)
    manager.close()
    assert c.get('/api/v1/profile', headers=headers(token)).status_code == 410


def test_capacity_rate_limits_and_active_session_cleanup(tmp_path, template):
    now = [0.0]
    manager = DemoSessions(tmp_path/'bounded', template, clock=lambda: now[0], capacity=1)
    token = manager.create('first')
    with pytest.raises(DemoError) as full:
        manager.create('second')
    assert full.value.code == 'demo_capacity'
    with manager.acquire(token):
        now[0] = 1801
        with pytest.raises(DemoError): manager.create('second')
        assert token in manager.entries
    second = manager.create('second')
    assert token not in manager.entries
    with pytest.raises(DemoError):
        with manager.acquire('../../private.db'): pass
    for _ in range(2): second = manager.create('second', replace=second)
    with pytest.raises(DemoError) as limited: manager.create('second', replace=second)
    assert limited.value.status == 429
    now[0] += 7201
    with pytest.raises(DemoError):
        with manager.acquire(second): pass
    manager.close()


def test_public_entrypoint_bootstraps_without_opening_configured_private_db(tmp_path):
    import os, socket, subprocess, sys, time
    import httpx
    private = tmp_path/'private.db'; private.write_bytes(b'private sentinel')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{private}', 'OPENAI_API_KEY': 'must-not-be-used',
           'REQUIREMENT_EXTRACTOR_PROVIDER': 'openai', 'JOBLENS_DEMO_PROXY_SECRET': SECRET,
           'JOBLENS_DEMO_FRONTEND_ORIGIN': ORIGIN}
    with (tmp_path/'startup.log').open('w+') as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.demo.public_main:app', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'], env=env, stdout=log, stderr=log)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False) as c:
                for _ in range(100):
                    assert process.poll() is None, 'Public deployment entrypoint failed startup'
                    try:
                        if c.get('/api/v1/health', timeout=.2).status_code == 200: break
                    except httpx.HTTPError: pass
                    time.sleep(.1)
                else: pytest.fail('Public entrypoint did not become ready')
                token = create(c)
                assert c.get('/api/v1/readiness', headers=headers(token)).status_code == 200
                assert c.get('/api/v1/jobs', headers=headers(token)).json()['total'] == 3
                assert c.post('/api/v1/job-imports/manual', headers=headers(token), json={}).status_code == 403
            assert private.read_bytes() == b'private sentinel'
        finally:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
