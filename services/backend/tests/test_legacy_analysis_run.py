"""Legacy workspaces use the same durable rule execution, never a model."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from app.db.models import ApplicationWorkspaceORM
from app.application.rule_match import _NoModel
from .test_career_agent_analysis_snapshot import synthetic_api, approve
from .test_workspace_feedback_transactions import _setup, _propose
from .test_analysis_update_plan import _dump


def _prepare(client, factory, ids):
    root, item = _setup(client, factory, ids)
    with factory.begin() as session:
        workspace = session.get(ApplicationWorkspaceORM, item['workspaceId'])
        workspace.current_analysis_thread_id = None
        workspace.current_analysis_result_id = None
    proposal = _propose(client, root)
    assert client.post(root + f"/evidence-proposals/{proposal['proposalId']}/confirm", json={'actorId':'local-user'}).status_code == 200
    plan = client.get(root + '/analysis-plan').json()
    return root, {'threadId':'legacy-new', 'runId':'legacy-run', 'requestId':'legacy-request', 'inputDigest':plan['inputDigest']}


def test_rule_run_replays_and_saves_new_analysis_without_fake_source(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    root, body = _prepare(client, factory, ids)
    forbidden = Mock(side_effect=AssertionError('provider must not execute'))
    monkeypatch.setattr(_NoModel, 'match', forbidden)
    response = client.post(root + '/analysis-runs', json=body)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['status'] == 'interrupted', state
    assert state['updateSteps'][0]['status'] == 'completed'
    assert state['updateSourceThreadId'] is None
    before = _dump(factory)
    assert client.post(root + '/analysis-runs', json=body).json() == state
    assert client.post(root + '/analysis-runs', json={**body,'inputDigest':'0'*64}).status_code == 409
    assert _dump(factory) == before
    resumed = approve(client, state)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['status'] == 'completed'
    result = client.get('/api/v1/career-agent/runs/legacy-new/result')
    assert result.status_code == 200 and result.json()['profileVersion'] == 2
    assert client.get('/api/v1/career-agent/runs/legacy-new/comparison').status_code == 409
    forbidden.assert_not_called()


def test_stale_preflight_never_creates_run(synthetic_api):
    client, factory, ids = synthetic_api
    root, body = _prepare(client, factory, ids)
    before = _dump(factory)
    response = client.post(root + '/analysis-runs', json={**body,'inputDigest':'0'*64})
    assert response.status_code == 409
    assert client.get('/api/v1/career-agent/runs/legacy-new').status_code == 404
    assert _dump(factory) == before


def test_concurrent_identical_starts_make_one_report(synthetic_api):
    from sqlalchemy import select, func
    from app.db.models import MatchReportORM
    client, factory, ids = synthetic_api
    root, body = _prepare(client, factory, ids)
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(MatchReportORM))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(root + '/analysis-runs', json=body), range(2)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(MatchReportORM)) == before + 1
    assert client.get('/api/v1/career-agent/runs/legacy-new').json()['status'] == 'interrupted'


def test_linkage_change_after_preflight_never_creates_run(synthetic_api):
    client, factory, ids = synthetic_api
    root, body = _prepare(client, factory, ids)
    workspace_id = root.rsplit('/', 1)[-1]
    with factory.begin() as session:
        workspace = session.get(ApplicationWorkspaceORM, workspace_id)
        workspace.current_analysis_thread_id = 'feedback_transaction'
    before = _dump(factory)
    assert client.post(root + '/analysis-runs', json=body).status_code == 409
    assert _dump(factory) == before


def test_report_save_failure_can_be_continued_without_partial_report(synthetic_api):
    from sqlalchemy import text
    from .test_bounded_analysis_update import _count, _continue
    client, factory, ids = synthetic_api
    root, body = _prepare(client, factory, ids)
    count = _count(factory)
    with factory.begin() as session:
        session.execute(text("CREATE TRIGGER fail_legacy_report BEFORE INSERT ON match_reports BEGIN SELECT RAISE(ABORT, 'private failure'); END"))
    response = client.post(root + '/analysis-runs', json=body)
    assert response.status_code == 503 and 'private failure' not in response.text
    state = client.get('/api/v1/career-agent/runs/legacy-new').json()
    assert state['updateSteps'][0]['status'] == 'running' and _count(factory) == count
    with factory.begin() as session:
        session.execute(text('DROP TRIGGER fail_legacy_report'))
    resumed = _continue(client, state)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['status'] == 'interrupted' and _count(factory) == count + 1


def test_requires_model_is_held_without_provider_call(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    root, body = _prepare(client, factory, ids)
    updated = client.put('/api/v1/profile', json=dict(expectedVersion=2, headline='Synthetic facts', yearsOfExperience=5,
        evidence=[dict(key='actual', type='project', summary='Implemented a Python backend outcome', source='Synthetic test repository')],
        skills=[dict(name='TypeScript', level='strong', evidenceKeys=['actual'])]))
    assert updated.status_code == 200, updated.text
    body['inputDigest'] = client.get(root + '/analysis-plan').json()['inputDigest']
    forbidden = Mock(side_effect=AssertionError('must not call model'))
    monkeypatch.setattr(_NoModel, 'match', forbidden)
    response = client.post(root + '/analysis-runs', json=body)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['updateSteps'][0]['status'] == 'requires_model'
    assert not state['pendingApproval']
    forbidden.assert_not_called()


def test_linkage_changed_after_interrupted_write_marks_run_stale(synthetic_api):
    from sqlalchemy import text
    from .test_bounded_analysis_update import _count, _continue
    client, factory, ids = synthetic_api
    root, body = _prepare(client, factory, ids)
    count = _count(factory)
    with factory.begin() as session:
        session.execute(text("CREATE TRIGGER fail_legacy_report BEFORE INSERT ON match_reports BEGIN SELECT RAISE(ABORT, 'simulated'); END"))
    assert client.post(root + '/analysis-runs', json=body).status_code == 503
    state = client.get('/api/v1/career-agent/runs/legacy-new').json()
    with factory.begin() as session:
        session.execute(text('DROP TRIGGER fail_legacy_report'))
        workspace = session.get(ApplicationWorkspaceORM, root.rsplit('/', 1)[-1])
        workspace.current_analysis_thread_id = 'feedback_transaction'
    resumed = _continue(client, state)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['status'] == 'stale' and _count(factory) == count


def test_start_request_shared_schema_matches_python():
    import json
    from pathlib import Path
    from app.api.v1.schemas.analysis_update import LegacyWorkspaceAnalysisStartRequest
    schema = json.loads((Path(__file__).parents[3] / 'packages/contracts/schemas/legacy-workspace-analysis-start.schema.json').read_text())
    del schema['$schema'], schema['$id']
    assert schema == LegacyWorkspaceAnalysisStartRequest.model_json_schema(by_alias=True)


def test_workspace_linked_during_rule_compute_does_not_save_report(synthetic_api, monkeypatch):
    from app.application.rule_match import BuildPinnedRuleMatch
    from .test_bounded_analysis_update import _count
    client, factory, ids = synthetic_api
    root, body = _prepare(client, factory, ids)
    count = _count(factory)
    actual = BuildPinnedRuleMatch.execute
    def race(self, **facts):
        result = actual(self, **facts)
        with factory.begin() as session:
            workspace = session.get(ApplicationWorkspaceORM, root.rsplit('/', 1)[-1])
            workspace.current_analysis_thread_id = 'feedback_transaction'
        return result
    monkeypatch.setattr(BuildPinnedRuleMatch, 'execute', race)
    response = client.post(root + '/analysis-runs', json=body)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'stale' and _count(factory) == count


def test_partial_link_cannot_be_treated_as_legacy(synthetic_api):
    client, factory, ids = synthetic_api
    root, body = _prepare(client, factory, ids)
    with factory.begin() as session:
        workspace = session.get(ApplicationWorkspaceORM, root.rsplit('/', 1)[-1])
        workspace.current_analysis_result_id = 'some-saved-result'
    before = _dump(factory)
    assert client.get(root + '/analysis-plan').status_code == 409
    assert client.post(root + '/analysis-runs', json=body).status_code == 409
    assert _dump(factory) == before
