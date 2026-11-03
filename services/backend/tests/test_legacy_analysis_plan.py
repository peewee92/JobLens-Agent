"""The historical workspace preflight is read-only and cannot call a provider."""
from unittest.mock import Mock
from app.db.models import ApplicationWorkspaceORM
from app.workflows.semantic_match import SemanticMatchWorkflow
from .test_career_agent_analysis_snapshot import synthetic_api
from .test_workspace_feedback_transactions import _setup, _propose
from .test_analysis_update_plan import _dump


def test_legacy_workspace_plan_reflects_current_facts_without_writes(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    root, item = _setup(client, factory, ids)
    assert client.get(root + '/analysis-plan').status_code == 409
    with factory.begin() as session:
        workspace = session.get(ApplicationWorkspaceORM, item['workspaceId'])
        workspace.current_analysis_thread_id = None
        workspace.current_analysis_result_id = None
    forbidden = Mock(side_effect=AssertionError('preflight must not run model'))
    monkeypatch.setattr(SemanticMatchWorkflow, 'execute', forbidden)
    before = _dump(factory)
    response = client.get(root + '/analysis-plan')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['workspaceId'] == item['workspaceId'] and data['advisoryOnly'] is True
    assert data['item']['jobId'] == ids[0] and data['item']['status'] == 'reuse'
    assert 'sourceResultId' not in data
    assert _dump(factory) == before
    proposal = _propose(client, root)
    assert client.post(root + f"/evidence-proposals/{proposal['proposalId']}/confirm", json={'actorId':'local-user'}).status_code == 200
    before = _dump(factory)
    changed = client.get(root + '/analysis-plan')
    assert changed.status_code == 200, changed.text
    data2 = changed.json()
    assert data2['profileVersion'] > data['profileVersion']
    assert data2['item']['status'] in {'ready', 'requires_model'}
    assert 'profile_changed' in data2['item']['staleReasons']
    assert data2['inputDigest'] != data['inputDigest']
    assert _dump(factory) == before
    forbidden.assert_not_called()


def test_missing_workspace_plan_is_not_empty_success(synthetic_api):
    client, _, _ = synthetic_api
    assert client.get('/api/v1/application-workspaces/missing/analysis-plan').status_code == 404


def test_legacy_plan_marks_semantic_work_as_unauthorized(synthetic_api, monkeypatch):
    from .test_analysis_update_plan import _profile
    client, factory, ids = synthetic_api
    root, item = _setup(client, factory, ids)
    with factory.begin() as session:
        workspace = session.get(ApplicationWorkspaceORM, item['workspaceId'])
        workspace.current_analysis_thread_id = None
        workspace.current_analysis_result_id = None
    _profile(client, semantic=True)
    forbidden = Mock(side_effect=AssertionError('must never call model'))
    monkeypatch.setattr(SemanticMatchWorkflow, 'execute', forbidden)
    before = _dump(factory)
    response = client.get(root + '/analysis-plan')
    assert response.status_code == 200, response.text
    item = response.json()['item']
    assert item['status'] == 'requires_model'
    assert 'model_authorization_required' in item['blockerCodes']
    assert _dump(factory) == before
    forbidden.assert_not_called()


def test_legacy_plan_shared_contract_matches_python():
    import json
    from pathlib import Path
    from app.api.v1.schemas.analysis_update import LegacyWorkspaceAnalysisPlanResponse
    schema = json.loads((Path(__file__).parents[3] / 'packages/contracts/schemas/legacy-workspace-analysis-plan.schema.json').read_text())
    del schema['$schema'], schema['$id']
    assert schema == LegacyWorkspaceAnalysisPlanResponse.model_json_schema(by_alias=True)
