"""User flags exclude current recommendations without deleting historical results."""
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, text
from app.db.models import JobORM
from app.repositories.sqlalchemy_job_availability import SqlAlchemyJobAvailability
from .test_career_agent_analysis_snapshot import synthetic_api, start, approve


def test_user_mark_invalidates_ranking_resume_and_preserves_history(synthetic_api):
    client, factory, ids = synthetic_api
    completed = start(client, ids, 'availability_history')
    assert approve(client, completed).json()['status'] == 'completed'
    original = client.get('/api/v1/career-agent/runs/availability_history/result').json()
    waiting = start(client, ids, 'availability_waiting')
    path = f'/api/v1/jobs/{ids[0]}/user-availability'
    request = {'userMarkedInactive': True, 'expectedRevision': 0}
    changed = client.put(path, json=request)
    assert changed.status_code == 200 and changed.json()['availabilityRevision'] == 1
    assert client.put(path, json={'userMarkedInactive': 'true', 'expectedRevision': 1}).status_code == 422
    assert client.put(path, json={'userMarkedInactive': False, 'expectedRevision': 1, 'extra': 1}).status_code == 422
    from jsonschema import Draft202012Validator
    import json
    from pathlib import Path
    schema = json.loads((Path(__file__).parents[3] / 'packages/contracts/schemas/job-user-availability.schema.json').read_text())
    Draft202012Validator(schema).validate(changed.json())
    request_schema = json.loads((Path(__file__).parents[3] / 'packages/contracts/schemas/job-user-availability-request.schema.json').read_text())
    Draft202012Validator(request_schema).validate(request)
    assert client.put(path, json=request).json() == changed.json()
    assert client.put(path, json={'userMarkedInactive': False, 'expectedRevision': 0}).status_code == 409
    detail = client.get(f'/api/v1/jobs/{ids[0]}').json()
    assert detail['userMarkedInactive'] is True and detail['availabilityRevision'] == 1
    result = client.get('/api/v1/match-ranking/preflight', params=[('jobId', j) for j in ids[:2]]).json()
    assert [item['jobId'] for item in result['items']] == [ids[1]]
    assert any('job_user_marked_inactive' in item['staleReasons'] for item in result['omissions'])
    history = client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items'][0]
    assert not history['isCurrent'] and 'job_user_marked_inactive' in history['staleReasons']
    history_schema = json.loads((Path(__file__).parents[3] / 'packages/contracts/schemas/match-report-history.schema.json').read_text())
    Draft202012Validator(history_schema['properties']['items']['items']['properties']['staleReasons']).validate(history['staleReasons'])
    saved = client.get('/api/v1/career-agent/runs/availability_history/result').json()
    assert not saved['isCurrent'] and saved['preparations'] == original['preparations']
    assert any('job_user_marked_inactive' in reason for reason in saved['staleReasons'])
    assert approve(client, waiting).json()['status'] == 'stale'
    plan = client.get('/api/v1/career-agent/runs/availability_history/update-plan').json()
    assert any(item['jobId'] == ids[0] and item['status'] == 'input_blocked'
               and 'job_user_marked_inactive' in item['blockerCodes'] for item in plan['items'])
    assert client.put(path, json={'userMarkedInactive': False, 'expectedRevision': 1}).json()['availabilityRevision'] == 2
    assert client.put(path, json=request).status_code == 409
    assert client.get(f'/api/v1/jobs/{ids[0]}/match-reports').json()['items'][0]['isCurrent']
    with factory() as session:
        assert session.scalar(select(JobORM.user_marked_inactive).where(JobORM.id == ids[0])) is False


def test_competing_writes_cannot_silently_overwrite(synthetic_api):
    _, factory, ids = synthetic_api
    repository = SqlAlchemyJobAvailability(factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: repository.set(ids[0], inactive=True, expected_revision=0), range(2)))
    assert all(item['availabilityRevision'] == 1 for item in results)
    assert repository.set(ids[0], inactive=False, expected_revision=0) is False


def test_failed_write_is_not_reported_as_success_and_can_be_retried(synthetic_api):
    client, factory, ids = synthetic_api
    with factory.begin() as session:
        session.execute(text("CREATE TRIGGER fail_user_availability BEFORE UPDATE OF user_marked_inactive ON jobs BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"))
    path = f'/api/v1/jobs/{ids[0]}/user-availability'
    request = {'userMarkedInactive': True, 'expectedRevision': 0}
    failed = client.put(path, json=request)
    assert failed.status_code == 503 and failed.json()['error']['retryable'] is True
    assert 'synthetic failure' not in failed.text
    assert client.get(f'/api/v1/jobs/{ids[0]}').json()['userMarkedInactive'] is False
    with factory.begin() as session:
        session.execute(text('DROP TRIGGER fail_user_availability'))
    assert client.put(path, json=request).json()['availabilityRevision'] == 1


def test_marked_job_cannot_create_new_execution_from_old_analysis(synthetic_api):
    from .test_analysis_start_execution import _completed, _counts
    client, factory, ids = synthetic_api
    body = _completed(client, ids)
    before = _counts(factory)
    assert client.put(f'/api/v1/jobs/{ids[0]}/user-availability', json={
        'userMarkedInactive': True, 'expectedRevision': 0}).status_code == 200
    result = client.post('/api/v1/career-agent/runs/execution/execution', json=body)
    assert result.status_code == 409 and result.json()['error']['code'] == 'analysis_execution_facts_stale'
    assert _counts(factory) == before


def test_inactive_job_blocks_all_new_match_entry_points_without_provider_or_new_report(synthetic_api, monkeypatch):
    from unittest.mock import Mock
    from sqlalchemy import func
    from app.db.models import MatchReportORM
    from app.workflows.semantic_match import SemanticMatchWorkflow
    client, factory, ids = synthetic_api
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(MatchReportORM))
    assert client.put(f'/api/v1/jobs/{ids[0]}/user-availability', json={
        'userMarkedInactive': True, 'expectedRevision': 0}).status_code == 200
    provider = Mock(side_effect=AssertionError('inactive job must not call semantic workflow'))
    monkeypatch.setattr(SemanticMatchWorkflow, 'execute', provider)
    for endpoint in ('semantic-match', 'match-report'):
        response = client.post(f'/api/v1/jobs/{ids[0]}/{endpoint}')
        assert response.status_code == 409, response.text
        assert response.json()['error']['code'] == 'job_user_marked_inactive'
    result = client.post('/api/v1/match-batch', json={'jobIds': [ids[0]]})
    assert result.status_code == 200, result.text
    assert result.json()['items'][0]['status'] == 'input_blocked'
    assert result.json()['items'][0]['blockerCodes'] == ['job_user_marked_inactive']
    assert result.json()['providerCalls'] == 0
    provider.assert_not_called()
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(MatchReportORM)) == before
    assert client.get(f'/api/v1/jobs/{ids[0]}/match-reports').status_code == 200


def test_report_transaction_rejects_change_during_computation_even_if_restored(synthetic_api):
    import pytest
    from app.application.job_availability_guard import JobUnavailableForMatchingError
    from app.repositories.sqlalchemy_match_report_unit_of_work import SqlAlchemyMatchReportUnitOfWork
    _, factory, ids = synthetic_api
    repository = SqlAlchemyJobAvailability(factory)
    assert repository.set(ids[0], inactive=True, expected_revision=0)
    assert repository.set(ids[0], inactive=False, expected_revision=1)
    with pytest.raises(JobUnavailableForMatchingError):
        with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
            uow.ensure_job_availability(ids[0], 0)
            uow.commit()
    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        uow.ensure_job_availability(ids[0], 2)
        uow.commit()


def test_report_is_not_saved_if_availability_changes_while_computing(synthetic_api, monkeypatch):
    from dataclasses import dataclass
    from sqlalchemy import func
    import pytest
    import app.application.match_report.use_case as report_module
    from app.application.job_availability_guard import JobUnavailableForMatchingError
    from app.application.match_report.use_case import BuildJobMatchReportUseCase
    from app.db.models import MatchReportORM
    from app.repositories.sqlalchemy_job_query_repository import SqlAlchemyJobQueryRepository
    from app.repositories.sqlalchemy_match_report_unit_of_work import SqlAlchemyMatchReportUnitOfWork
    _, factory, ids = synthetic_api
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(MatchReportORM))
    @dataclass(frozen=True)
    class SyntheticReport:
        db_writes: int = 0
    class Runner:
        def execute(self, job_id):
            SqlAlchemyJobAvailability(factory).set(job_id, inactive=True, expected_revision=0)
            return object()
    monkeypatch.setattr(report_module, 'build_match_report', lambda _: SyntheticReport())
    use_case = BuildJobMatchReportUseCase(Runner(), jobs=SqlAlchemyJobQueryRepository(factory),
        uow_factory=lambda: SqlAlchemyMatchReportUnitOfWork(factory))
    with pytest.raises(JobUnavailableForMatchingError):
        use_case.execute(ids[0])
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(MatchReportORM)) == before


def test_batch_continues_after_an_inactive_job(synthetic_api, monkeypatch):
    from unittest.mock import Mock
    from app.workflows.semantic_match import SemanticMatchWorkflow
    client, _, ids = synthetic_api
    assert client.put(f'/api/v1/jobs/{ids[0]}/user-availability', json={
        'userMarkedInactive': True, 'expectedRevision': 0}).status_code == 200
    workflow = Mock(side_effect=RuntimeError('offline test: no model call'))
    monkeypatch.setattr(SemanticMatchWorkflow, 'execute', workflow)
    response = client.post('/api/v1/match-batch', json={'jobIds': ids[:2]})
    assert response.status_code == 200, response.text
    first, second = response.json()['items']
    assert first['status'] == 'input_blocked'
    assert first['blockerCodes'] == ['job_user_marked_inactive']
    assert second['jobId'] == ids[1] and second['status'] == 'failed'
    assert workflow.call_count == 1


def test_active_job_can_save_new_report_in_guarded_transaction(synthetic_api, monkeypatch):
    from sqlalchemy import func
    import app.application.match_report.use_case as report_module
    from app.application.match_report.use_case import BuildJobMatchReportUseCase
    from app.db.models import MatchReportORM
    from app.repositories.sqlalchemy_job_query_repository import SqlAlchemyJobQueryRepository
    from app.repositories.sqlalchemy_match_report_repository import SqlAlchemyMatchReportQueryRepository
    from app.repositories.sqlalchemy_match_report_unit_of_work import SqlAlchemyMatchReportUnitOfWork
    _, factory, ids = synthetic_api
    original = SqlAlchemyMatchReportQueryRepository(factory).list_for_job(ids[0])[0].report
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(MatchReportORM))
    class OfflineRunner:
        def execute(self, job_id):
            return object()
    monkeypatch.setattr(report_module, 'build_match_report', lambda _: original)
    result = BuildJobMatchReportUseCase(OfflineRunner(), jobs=SqlAlchemyJobQueryRepository(factory),
        uow_factory=lambda: SqlAlchemyMatchReportUnitOfWork(factory)).execute(ids[0])
    assert result.db_writes == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(MatchReportORM)) == before + 1


def test_batch_marks_side_effect_counts_uncertain_if_availability_changes_after_planning():
    from types import SimpleNamespace
    from app.application.job_availability_guard import JobUnavailableForMatchingError
    from app.application.match_batch_execution import ExecuteBatchMatchUseCase
    from app.application.match_batch_planning import BatchMatchPlanStatus
    class Planner:
        def execute(self, job_ids):
            return SimpleNamespace(items=[SimpleNamespace(job_id=job, status=BatchMatchPlanStatus.READY) for job in job_ids])
    class Runner:
        def execute(self, job_id):
            if job_id == 'first':
                raise JobUnavailableForMatchingError('changed', code='job_availability_changed')
            return SimpleNamespace(db_writes=1, provider_calls=0, trace_runs_created=0)
    result = ExecuteBatchMatchUseCase(planner=Planner(), report_runner=Runner()).execute(('first', 'second'))
    assert result.items[0].blocker_codes == ('job_availability_changed',)
    assert result.items[1].status == 'succeeded'
    assert result.side_effect_counts_complete is False
    assert result.db_writes == 1


def test_inactive_requirement_extraction_blocks_before_workflow(synthetic_api, monkeypatch):
    from unittest.mock import Mock
    from sqlalchemy import func
    from app.db.models import JobRequirementExtractionORM
    from app.workflows.job_requirement_extraction import ExtractJobRequirementsWorkflow
    client, factory, ids = synthetic_api
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(JobRequirementExtractionORM))
    assert client.put(f'/api/v1/jobs/{ids[0]}/user-availability', json={
        'userMarkedInactive': True, 'expectedRevision': 0}).status_code == 200
    workflow = Mock(side_effect=AssertionError('inactive job must not call workflow'))
    monkeypatch.setattr(ExtractJobRequirementsWorkflow, 'execute', workflow)
    response = client.post(f'/api/v1/jobs/{ids[0]}/requirement-extractions', json={'confirmLiveCost': True})
    assert response.status_code == 409, response.text
    assert response.json()['error']['code'] == 'job_user_marked_inactive'
    workflow.assert_not_called()
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(JobRequirementExtractionORM)) == before
    assert client.get(f'/api/v1/jobs/{ids[0]}/requirements').status_code == 200


def test_requirement_extraction_state_change_during_computation_does_not_save(synthetic_api, monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy import func
    from app.db.models import JobRequirementExtractionORM
    from app.workflows.job_requirement_extraction import ExtractJobRequirementsWorkflow
    client, factory, ids = synthetic_api
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(JobRequirementExtractionORM))
    def extract_then_change(self, *, job_id, description):
        repository = SqlAlchemyJobAvailability(factory)
        assert repository.set(job_id, inactive=True, expected_revision=0)
        assert repository.set(job_id, inactive=False, expected_revision=1)
        return SimpleNamespace(extractor_version='fixture', model=None, prompt_version='fixture',
                               trace_run_id=None, provider_calls=0, requirements=())
    monkeypatch.setattr(ExtractJobRequirementsWorkflow, 'execute', extract_then_change)
    response = client.post(f'/api/v1/jobs/{ids[0]}/requirement-extractions', json={'confirmLiveCost': True})
    assert response.status_code == 409, response.text
    assert response.json()['error']['code'] == 'job_availability_changed'
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(JobRequirementExtractionORM)) == before


def test_requirement_extraction_does_not_save_if_job_description_changes(synthetic_api, monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy import func
    from app.db.models import JobRequirementExtractionORM
    from app.workflows.job_requirement_extraction import ExtractJobRequirementsWorkflow
    client, factory, ids = synthetic_api
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(JobRequirementExtractionORM))
        old_id = session.scalar(select(JobRequirementExtractionORM.id).where(
            JobRequirementExtractionORM.job_id == ids[0]).order_by(JobRequirementExtractionORM.created_at.desc()))
    def extract_then_import(self, *, job_id, description):
        with factory.begin() as session:
            session.get(JobORM, job_id).description = description + ' Updated description.'
        return SimpleNamespace(extractor_version='fixture', model=None, prompt_version='fixture',
                               trace_run_id=None, provider_calls=0, requirements=())
    monkeypatch.setattr(ExtractJobRequirementsWorkflow, 'execute', extract_then_import)
    response = client.post(f'/api/v1/jobs/{ids[0]}/requirement-extractions', json={'confirmLiveCost': True})
    assert response.status_code == 409, response.text
    assert response.json()['error']['code'] == 'job_description_changed_during_extraction'
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(JobRequirementExtractionORM)) == before
        assert session.get(JobRequirementExtractionORM, old_id) is not None


def test_two_concurrent_requirement_extractions_only_one_can_save(synthetic_api):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from types import SimpleNamespace
    from sqlalchemy import func
    from app.application.job_requirements.errors import RequirementExtractionSupersededError
    from app.application.job_requirements.use_cases import ExtractJobRequirementsUseCase
    from app.db.models import JobRequirementExtractionORM
    from app.repositories.sqlalchemy_job_query_repository import SqlAlchemyJobQueryRepository
    from app.repositories.sqlalchemy_job_requirement_repository import SqlAlchemyJobRequirementQueryRepository
    from app.repositories.sqlalchemy_job_requirement_unit_of_work import SqlAlchemyJobRequirementUnitOfWork
    _, factory, ids = synthetic_api
    jobs = SqlAlchemyJobQueryRepository(factory)
    query = SqlAlchemyJobRequirementQueryRepository(factory)
    previous = query.get_latest(ids[0])
    assert previous and previous.requirements
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(JobRequirementExtractionORM))
    barrier = Barrier(2, timeout=10)
    class OfflineWorkflow:
        def execute(self, *, job_id, description):
            barrier.wait()
            return SimpleNamespace(extractor_version=previous.extractor_version, model=previous.model,
                prompt_version=previous.prompt_version, trace_run_id=previous.trace_run_id,
                provider_calls=0, requirements=previous.requirements)
    def run(_):
        try:
            return ExtractJobRequirementsUseCase(jobs=jobs, query_repository=query,
                workflow=OfflineWorkflow(), provider=previous.provider,
                uow_factory=lambda: SqlAlchemyJobRequirementUnitOfWork(factory)).execute(ids[0])
        except RequirementExtractionSupersededError as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    failures = [item for item in results if isinstance(item, RequirementExtractionSupersededError)]
    successes = [item for item in results if not isinstance(item, Exception)]
    assert len(failures) == len(successes) == 1
    assert query.get_latest(ids[0]).extraction_id == successes[0].extraction_id
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(JobRequirementExtractionORM)) == before + 1


def test_superseded_extraction_http_returns_specific_conflict(synthetic_api, monkeypatch):
    from unittest.mock import Mock
    from app.application.job_requirements.errors import RequirementExtractionSupersededError
    from app.workflows.job_requirement_extraction import ExtractJobRequirementsWorkflow
    client, _, ids = synthetic_api
    monkeypatch.setattr(ExtractJobRequirementsWorkflow, 'execute', Mock(
        side_effect=RequirementExtractionSupersededError('another result already saved')))
    response = client.post(f'/api/v1/jobs/{ids[0]}/requirement-extractions', json={'confirmLiveCost': True})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'requirement_extraction_superseded'
