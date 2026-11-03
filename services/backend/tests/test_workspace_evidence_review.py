"""Actual preparation actions, HTTP handlers and disposable SQLite; no paid provider."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json
from pathlib import Path

from sqlalchemy import select, func
from app.db.models import EvidenceProposalORM, ExecutionActionItemORM
from .test_career_agent_analysis_snapshot import synthetic_api
from .test_analysis_start_execution import _completed
from .test_workspace_feedback_transactions import _profiles, _event_count


def _ordinary_actions(client, factory, ids, thread='ordinary'):
    body = _completed(client, ids, thread)
    response = client.post(f'/api/v1/career-agent/runs/{thread}/execution', json=body)
    assert response.status_code == 200, response.text
    item = response.json()['items'][0]
    root = f"/api/v1/application-workspaces/{item['workspaceId']}"
    for action in item['actionIds']:
        with factory() as session:
            assert session.get(ExecutionActionItemORM, action).source_gap_capability is None
        done = client.post(f'{root}/actions/{action}/status', json={
            'actorId': 'local-user', 'expectedStatus': 'todo', 'newStatus': 'done'})
        assert done.status_code == 200, done.text
    context = client.get(f'{root}/evidence-context')
    assert context.status_code == 200, context.text
    return root, item, context.json()


def _body(context, key='ordinary_fact', index=0):
    return dict(actorId='local-user', idempotencyKey=key, evidenceType='project',
        evidenceSummary=f'Synthetic actual outcome {key}', evidenceSource='Synthetic reproducible test repository',
        skillLevel='unknown', requirementId=context['actionSources'][index]['options'][0][0],
        expectedProfileId=context['currentProfileId'], expectedProfileVersion=context['currentProfileVersion'],
        reviewedCurrentProfile=True)


def _propose(client, root, context, key='ordinary_fact', index=0):
    action = context['actionSources'][index]['actionId']
    response = client.post(f'{root}/actions/{action}/evidence-proposals', json=_body(context, key, index))
    assert response.status_code == 201, response.text
    return response.json()


def _confirm(client, root, proposal):
    return client.post(f"{root}/evidence-proposals/{proposal['proposalId']}/confirm", json={'actorId': 'local-user'})


def test_ordinary_preparation_action_can_propose_but_only_confirmation_changes_profile(synthetic_api):
    client, factory, ids = synthetic_api
    root, item, context = _ordinary_actions(client, factory, ids)
    assert len(context['actionSources']) == 2 and not context['blockedActionIds']
    assert _profiles(factory) == 1  # Completing every action never confirms new facts.
    proposal = _propose(client, root, context)
    assert proposal['sourceAnalysisThreadId'] == 'ordinary'
    assert proposal['sourceProfileVersion'] == proposal['confirmationBaseProfileVersion'] == 1
    assert proposal['sourceRequirementIds'] == [_body(context)['requirementId']]
    assert proposal['status'] == 'pending_confirmation' and _profiles(factory) == 1
    confirmed = _confirm(client, root, proposal)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['confirmedProfileVersion'] == 2
    assert _confirm(client, root, proposal).json() == confirmed.json()
    assert _profiles(factory) == 2 and _event_count(factory, 'evidence_confirmed') == 1
    current = client.get('/api/v1/profile').json()
    assert next(s for s in current['skills'] if s['name'] == 'Python')['level'] == 'strong'
    saved = client.get('/api/v1/career-agent/runs/ordinary/result').json()
    assert saved['profileVersion'] == 1 and not saved['isCurrent']
    assert client.get(f'{root}/preparation').json()['preparation']['profileVersion'] == 1


def test_requirement_review_and_idempotency_are_checked_in_actual_commands(synthetic_api):
    client, factory, ids = synthetic_api
    root, _, context = _ordinary_actions(client, factory, ids)
    path = f"{root}/actions/{context['actionSources'][0]['actionId']}/evidence-proposals"
    body = _body(context)
    for update, code in (({'requirementId': 'foreign_requirement'}, 'evidence_proposal_requirement_invalid'),
                         ({'reviewedCurrentProfile': False}, 'evidence_proposal_review_required'),
                         ({'expectedProfileVersion': 9}, 'evidence_proposal_profile_stale')):
        response = client.post(path, json={**body, **update})
        assert response.status_code == 409 and response.json()['detail'] == code
    proposal = _propose(client, root, context)
    assert client.post(path, json=body).json() == proposal
    for update in ({'reviewedCurrentProfile': False}, {'evidenceSource': 'Changed claim'}, {'expectedProfileVersion': 9}):
        response = client.post(path, json={**body, **update})
        assert response.status_code == 409 and response.json()['detail'] == 'evidence_proposal_idempotency_conflict'
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(EvidenceProposalORM)) == 1
    assert _profiles(factory) == 1


def test_stale_proposal_explicitly_reconsidered_without_rewriting_original_and_one_confirmation_per_origin(synthetic_api):
    client, factory, ids = synthetic_api
    root, _, context = _ordinary_actions(client, factory, ids)
    original = _propose(client, root, context, 'first')
    other = _propose(client, root, context, 'second', index=1)
    assert _confirm(client, root, other).status_code == 200
    assert _confirm(client, root, original).status_code == 409
    current = client.get(f'{root}/evidence-context').json()
    path = f"{root}/evidence-proposals/{original['proposalId']}/reconsider"
    body = dict(actorId='local-user', idempotencyKey='reviewed_again', expectedProfileId=current['currentProfileId'],
        expectedProfileVersion=2, reviewedCurrentProfile=True)
    assert client.post(path, json={**body, 'reviewedCurrentProfile': False}).status_code == 409
    replacements = []
    for key in ('reviewed_again', 'another_review'):
        result = client.post(path, json={**body, 'idempotencyKey': key})
        assert result.status_code == 200, result.text
        replacements.append(result.json())
    new = replacements[0]
    assert new['proposalId'] != original['proposalId'] and new['originProposalId'] == original['proposalId']
    assert new['sourceProfileVersion'] == 1 and new['confirmationBaseProfileVersion'] == 2
    assert new['evidenceSummary'] == original['evidenceSummary']
    assert client.get(f'{root}/overview').json()['evidencePendingConfirmation'] == 1
    assert client.post(path, json=body).json() == new
    assert client.post(path, json={**body, 'reviewedCurrentProfile': False}).status_code == 409
    barrier = Barrier(2)
    def confirm(proposal):
        barrier.wait(timeout=5)
        return _confirm(client, root, proposal)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(confirm, replacements))
    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    assert _profiles(factory) == 3 and _event_count(factory, 'evidence_confirmed') == 2
    assert client.get(f'{root}/overview').json()['evidencePendingConfirmation'] == 0
    with factory() as session:
        old = session.get(EvidenceProposalORM, original['proposalId'])
        assert old.status == 'pending_confirmation' and old.confirmation_base_profile_version == 1
        assert old.evidence_summary == original['evidenceSummary']
    assert client.post(path, json={**body, 'idempotencyKey': 'after_confirmed'}).status_code == 409
    replay = client.post(path, json=body)
    assert replay.status_code == 200  # Original command receipt, not a new fact.


def test_new_analysis_actions_use_own_origin_not_workspace_initial_snapshot(synthetic_api):
    client, factory, ids = synthetic_api
    root, first, context = _ordinary_actions(client, factory, ids)
    proposal = _propose(client, root, context)
    assert _confirm(client, root, proposal).status_code == 200
    for job in ids[:2]:
        response = client.post(f'/api/v1/jobs/{job}/match-report')
        assert response.status_code == 200, response.text
    new_root, item, new_context = _ordinary_actions(client, factory, ids, 'new_analysis')
    assert new_root == root and item['workspaceId'] == first['workspaceId']
    sources = [s for s in new_context['actionSources'] if s['threadId'] == 'new_analysis']
    assert len(sources) == 2 and all(s['profileVersion'] == 2 for s in sources)
    new_context = {**new_context, 'actionSources': sources}
    fresh = _propose(client, root, new_context, 'fresh_v2')
    assert fresh['sourceProfileVersion'] == fresh['confirmationBaseProfileVersion'] == 2
    assert fresh['sourceAnalysisThreadId'] == 'new_analysis'


def test_broken_action_source_is_blocked_without_erasing_other_ready_sources(synthetic_api):
    client, factory, ids = synthetic_api
    root, item, context = _ordinary_actions(client, factory, ids)
    broken = context['actionSources'][0]['actionId']
    with factory.begin() as session:
        session.get(ExecutionActionItemORM, broken).source_analysis_result_id = 'wrong_saved_result'
    read = client.get(f'{root}/evidence-context').json()
    assert read['blockedActionIds'] == [broken] and len(read['actionSources']) == 1
    response = client.post(f'{root}/actions/{broken}/evidence-proposals', json=_body(context))
    assert response.status_code == 409 and response.json()['detail'] == 'evidence_proposal_action_source_invalid'
    assert _profiles(factory) == 1


def test_evidence_review_shared_contracts_match_python():
    from app.api.v1.schemas.application_workspace import (CreateEvidenceProposalRequest, EvidenceProposalResponse,
        ReconsiderEvidenceProposalRequest, EvidenceContextResponse)
    for name, model in [('create-evidence-proposal', CreateEvidenceProposalRequest), ('evidence-proposal', EvidenceProposalResponse),
                        ('reconsider-evidence-proposal', ReconsiderEvidenceProposalRequest), ('evidence-context', EvidenceContextResponse)]:
        schema = json.loads((Path(__file__).parents[3] / f'packages/contracts/schemas/{name}.schema.json').read_text())
        del schema['$schema'], schema['$id']
        assert schema == model.model_json_schema(by_alias=True)
