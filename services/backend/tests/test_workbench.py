"""Actual read-only SQLite/API projection, not a second stored progress model."""
import json
from pathlib import Path
from dataclasses import replace
from unittest.mock import Mock
from sqlalchemy import event, select
from app.application.workbench import GetWorkbenchUseCase, WorkbenchSnapshot, WorkbenchRun
from app.db.models import UserProfileORM, CareerAgentRunORM
from app.db.base import Base
from app.api.v1.schemas.workbench import WorkbenchResponse
from .test_career_agent_analysis_snapshot import synthetic_api, start, approve
from .test_analysis_start_execution import _counts


def test_workbench_projects_pending_saved_and_executing_without_writes(synthetic_api):
    client, factory, ids = synthetic_api
    statements = []
    engine = factory.kw['bind']
    def track(conn, cursor, statement, parameters, context, many):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(engine, 'before_cursor_execute', track)
    try:
        first = client.get('/api/v1/workbench')
        assert first.status_code == 200, first.text
        assert first.json()['snapshot']['jobCount'] == 20
        assert first.json()['nextAction']['code'] == 'analyze_jobs'
        assert not {'INSERT', 'UPDATE', 'DELETE'} & set(statements)
        state = start(client, ids, 'workbench')
        statements.clear()
        pending = client.get('/api/v1/workbench').json()
        assert pending['nextAction']['code'] == 'open_run'
        assert pending['snapshot']['currentRun']['status'] == 'interrupted'
        assert not {'INSERT', 'UPDATE', 'DELETE'} & set(statements)
        completed = approve(client, state).json()
        saved = client.get('/api/v1/workbench').json()
        assert saved['nextAction']['code'] == 'start_execution'
        assert saved['snapshot']['currentRun']['resultId'] == completed['resultId']
        result = client.post('/api/v1/career-agent/runs/workbench/execution', json={
            'commandId': 'workbench-exec', 'resultId': completed['resultId'], 'jobIds': ids[:2]})
        assert result.status_code == 200, result.text
        before = _counts(factory)
        statements.clear()
        executing = client.get('/api/v1/workbench').json()
        assert executing['nextAction']['code'] == 'continue_execution'
        assert len(executing['snapshot']['workspaces']) == 2
        assert executing['snapshot']['currentRun']['executionTargetCount'] == 2
        assert all(w['openActionCount'] == 2 for w in executing['snapshot']['workspaces'])
        assert len(executing['snapshot']['changes']) <= 10
        assert executing['snapshot']['changes']
        assert not {'INSERT', 'UPDATE', 'DELETE'} & set(statements)
        assert _counts(factory) == before
        with factory.begin() as session:
            session.add(UserProfileORM(id='workbench_new_profile', profile_key='default', version=2,
                headline='New confirmed but incomplete facts', years_of_experience=6))
        stale = client.get('/api/v1/workbench').json()
        assert stale['snapshot']['currentRun']['resultIsCurrent'] is False
        assert 'profile_evidence_missing' in stale['snapshot']['inputIssueCodes']
        assert stale['nextAction']['code'] == 'confirm_inputs'
        assert len(stale['snapshot']['workspaces']) == 2  # History remains accessible.
    finally:
        event.remove(engine, 'before_cursor_execute', track)


def test_empty_workbench_has_concrete_nonblocking_browse_path(synthetic_api):
    client, factory, _ = synthetic_api
    # This fixture is a disposable synthetic DB, never the user's career records.
    Base.metadata.drop_all(factory.kw['bind'])
    Base.metadata.create_all(factory.kw['bind'])
    response = client.get('/api/v1/workbench')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['nextAction']['href'] == '/profile'
    assert data['snapshot']['currentRun'] is None
    assert data['snapshot']['jobCount'] == 0
    assert data['snapshot']['workspaces'] == data['snapshot']['changes'] == []
    assert 'profile_missing' in data['snapshot']['inputIssueCodes']


def test_old_completed_run_does_not_fabricate_result_reference(synthetic_api):
    client, factory, ids = synthetic_api
    state = start(client, ids, 'legacy_workbench')
    assert approve(client, state).status_code == 200
    with factory.begin() as session:
        row = session.get(CareerAgentRunORM, 'legacy_workbench')
        row.analysis_result = None
    result = client.get('/api/v1/workbench').json()
    assert result['snapshot']['currentRun']['resultId'] is None
    assert result['snapshot']['currentRun']['resultIsCurrent'] is None
    assert result['nextAction']['code'] == 'analyze_jobs'


def test_next_step_uses_full_execution_count_not_bounded_display_count():
    from datetime import datetime, UTC
    run = WorkbenchRun('a b', 'completed', 'done', 2, 2, 2, 'saved', True, datetime.now(UTC))
    snapshot = WorkbenchSnapshot(1, 1, 1, (), 20, run, (), ())
    query = Mock(read=Mock(return_value=snapshot))
    assert GetWorkbenchUseCase(query).execute().next_action.code == 'analyze_jobs'
    query.read.return_value = replace(snapshot, current_run=replace(run, execution_target_count=1))
    assert GetWorkbenchUseCase(query).execute().next_action.href == '/agent/results/a%20b'
    query.read.return_value = replace(snapshot, current_run=replace(run, result_is_current=False))
    assert GetWorkbenchUseCase(query).execute().next_action.code == 'review_stale_analysis'
    from app.application.workbench import WorkbenchWorkspace
    query.read.return_value = replace(snapshot, current_run=replace(run, status="blocked", result_id=None),
        workspaces=(WorkbenchWorkspace("existing", "job", "Existing target", "preparing", 1, None),))
    assert GetWorkbenchUseCase(query).execute().next_action.code == 'repair_run'
    query.read.return_value = replace(snapshot, job_count=0, current_run=None)
    assert GetWorkbenchUseCase(query).execute().next_action.code == 'add_jobs'


def test_workbench_shared_schema_matches_python():
    path = Path(__file__).parents[3] / 'packages/contracts/schemas/workbench.schema.json'
    schema = json.loads(path.read_text())
    del schema['$schema'], schema['$id']
    assert schema == WorkbenchResponse.model_json_schema(by_alias=True)


def test_workbench_database_error_is_actionable_not_a_false_empty_success(synthetic_api):
    from sqlalchemy.exc import OperationalError
    from app.api.deps import get_workbench_use_case
    from app.main import app
    client, _, _ = synthetic_api
    app.dependency_overrides[get_workbench_use_case] = lambda: Mock(execute=Mock(
        side_effect=OperationalError('private SQL', {}, Exception('private database detail'))))
    try:
        response = client.get('/api/v1/workbench')
        assert response.status_code == 503
        assert response.json()['error']['retryable'] is True
        assert response.json()['error']['code'] == 'workbench_unavailable'
        assert 'private' not in response.text
    finally:
        app.dependency_overrides.pop(get_workbench_use_case)
