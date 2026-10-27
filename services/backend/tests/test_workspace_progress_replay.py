"""Actual HTTP/SQLite receipts used by browser transport recovery; no model."""
from .test_career_agent_analysis_snapshot import synthetic_api
from .test_workspace_feedback_transactions import _setup, _event_count
from .test_analysis_update_plan import _dump


def test_lost_status_response_replays_original_without_reverting_a_later_human_result(synthetic_api):
    client, factory, ids = synthetic_api
    root, item = _setup(client, factory, ids)
    original = dict(actorId='local-user', idempotencyKey='original_lost_response', expectedStatus='preparing', newStatus='applied')
    assert client.post(root+'/status', json=original).status_code == 200
    later = {**original, 'idempotencyKey':'later_human_result','expectedStatus':'applied','newStatus':'interviewing'}
    assert client.post(root+'/status',json=later).status_code == 200
    before = _dump(factory)
    replay = client.post(root+'/status', json=original)
    assert replay.status_code == 200 and replay.json()['status'] == 'interviewing'
    assert _event_count(factory, 'status_changed') == 2 and _dump(factory) == before
    assert client.post(root+'/status',json={**original,'newStatus':'withdrawn'}).status_code == 409
    assert _dump(factory) == before


def test_action_response_loss_exact_replay_and_late_older_progress_does_not_overwrite_done(synthetic_api):
    client, factory, ids = synthetic_api
    root, item = _setup(client, factory, ids)
    actions = client.get(root+'/actions').json()
    action = next(a for a in actions if a['status'] == 'todo')
    path = root+f"/actions/{action['actionId']}/status"
    start = dict(actorId='local-user',expectedStatus='todo',newStatus='in_progress')
    assert client.post(path,json=start).status_code == 200
    before = _dump(factory)
    assert client.post(path,json=start).status_code == 200 and _dump(factory) == before
    done = {**start,'expectedStatus':'in_progress','newStatus':'done'}
    assert client.post(path,json=done).status_code == 200
    before = _dump(factory)
    assert client.post(path,json=done).status_code == 200 and _dump(factory) == before
    assert client.post(path,json=start).status_code == 409 and _dump(factory) == before
    assert _event_count(factory,'action_completed') == 1


def test_linked_workspace_confirmed_fact_uses_saved_analysis_update_not_legacy_rematch(synthetic_api):
    from .test_workspace_feedback_transactions import _propose
    client, factory, ids = synthetic_api
    root, item = _setup(client, factory, ids)
    variants = client.get(root+'/resume-variants').json()
    response = client.post(root+f"/resume-variants/{variants[0]['variantId']}/review",json={'actorId':'local-user','expectedStatus':'draft'})
    assert response.status_code == 200, response.text
    proposal = _propose(client,root)
    assert client.post(root+f"/evidence-proposals/{proposal['proposalId']}/confirm",json={'actorId':'local-user'}).status_code == 200
    before = _dump(factory)
    overview = client.get(root+'/overview').json()
    assert overview['nextBestAction']['code'] == 'update_analysis'
    assert overview['nextBestAction']['href'] == '/agent/results/feedback_transaction/update'
    assert _dump(factory) == before


def test_workbench_keeps_partial_result_scope_truthful(synthetic_api):
    from .test_bounded_analysis_update import _begin, _continue
    from .test_career_agent_analysis_snapshot import approve
    client, factory, ids = synthetic_api
    state, _ = _begin(client,ids)
    partial = _continue(client,state,partial=True).json()
    assert approve(client,partial).json()['status'] == 'completed'
    before = _dump(factory)
    data = client.get('/api/v1/workbench').json()
    assert data['snapshot']['currentRun']['partial'] is True
    assert data['snapshot']['currentRun']['jobCount'] == 8
    assert data['snapshot']['currentRun']['completedReportCount'] == 5
    assert any(c['kind'] == 'analysis_partial' for c in data['snapshot']['changes'])
    assert _dump(factory) == before


def test_overview_does_not_keep_requesting_an_update_after_fact_was_included(synthetic_api):
    from unittest.mock import Mock
    from dataclasses import replace
    from app.application.application_workspace.overview import BuildApplicationWorkspaceOverviewUseCase
    from app.repositories.sqlalchemy_career_agent_checkpoint import SqlAlchemyCareerAgentCheckpointStore
    from .test_workspace_feedback_transactions import _propose
    client,factory,ids = synthetic_api
    root,item = _setup(client,factory,ids)
    proposal = _propose(client,root)
    assert client.post(root+f"/evidence-proposals/{proposal['proposalId']}/confirm",json={'actorId':'local-user'}).status_code == 200
    # Real update -> saved v2 -> reused workspace, not a synthetic state trajectory.
    source='feedback_transaction'
    plan=client.get(f'/api/v1/career-agent/runs/{source}/update-plan').json()
    state=client.post(f'/api/v1/career-agent/runs/{source}/updates',json={
        'threadId':'included','runId':'included_run','requestId':'included_req','sourceResultId':plan['sourceResultId'],
        'inputDigest':plan['inputDigest'],'scope':'targets','topN':2}).json()
    from .test_career_agent_analysis_snapshot import approve
    assert approve(client,state).json()['status']=='completed'
    result=client.get('/api/v1/career-agent/runs/included/result').json()
    assert result['profileVersion']==2
    executed=client.post('/api/v1/career-agent/runs/included/execution',json={'commandId':'included_exec','resultId':result['resultId'],'jobIds':result['selectedJobIds']})
    assert executed.status_code==200,executed.text
    before=_dump(factory)
    assert client.get(root+'/overview').json()['nextBestAction']['code'] not in {'update_analysis','rematch'}
    assert _dump(factory)==before
