"""Actual saved update HTTP + SQLite; pure snapshot variations explicitly synthetic."""
from dataclasses import replace
from pathlib import Path
import json
from unittest.mock import Mock
import pytest
from sqlalchemy import delete
from sqlalchemy.exc import OperationalError
from app.api import deps
from app.application.analysis_comparison import CompareSavedAnalysesUseCase, AnalysisComparisonError
from app.application.match_report import MatchRecommendation
from app.application.eligibility import RequirementFitStatus
from app.application.semantic_match import SemanticMatchVerdict
from app.application.rule_match import _NoModel
from app.db.models import MatchReportORM, UserProfileORM
from app.repositories.sqlalchemy_analysis_comparison import SqlAlchemyAnalysisComparisonReader
from .test_career_agent_analysis_snapshot import synthetic_api, approve
from .test_analysis_update_plan import _dump
from .test_bounded_analysis_update import _begin, _continue

URL = '/api/v1/career-agent/runs/updated/comparison'


def _saved(client, ids, partial=False):
    state, _ = _begin(client, ids)
    response = _continue(client, state, partial=partial)
    assert response.status_code == 200, response.text
    assert approve(client, response.json()).json()['status'] == 'completed'


def test_actual_saved_comparison_is_readonly_unchanged_and_immune_to_later_facts(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    _saved(client, ids)
    forbidden = Mock(side_effect=AssertionError('no model'))
    monkeypatch.setattr(_NoModel, 'match', forbidden)
    before = _dump(factory)
    response = client.get(URL)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['sourceThreadId'] == 'update_source'
    assert data['requestedJobIds'] == ids[:8] and data['rankingComparable']
    assert (data['previousProfileVersion'], data['currentProfileVersion']) == (1, 2)
    assert all(i['signal'] == 'unchanged' and i['rankChange'] == 0 for i in data['items'])
    assert all('evidence_references_changed' in i['reasonCodes'] for i in data['items'])
    assert _dump(factory) == before
    with factory.begin() as session:
        session.add(UserProfileORM(id='later', profile_key='default', version=3, headline='Later facts', years_of_experience=9))
    after = _dump(factory)
    assert client.get(URL).json() == data
    assert _dump(factory) == after
    assert client.get('/api/v1/career-agent/runs/updated/result').json()['updateSourceThreadId'] == 'update_source'
    forbidden.assert_not_called()


def test_partial_lists_missing_jobs_without_fabricated_rank_or_failure(synthetic_api):
    client, factory, ids = synthetic_api
    _saved(client, ids, partial=True)
    before = _dump(factory)
    data = client.get(URL).json()
    assert data['partial'] and not data['rankingComparable'] and len(data['items']) == 8
    assert all(i['rankChange'] is None for i in data['items'])
    assert all(i['signal'] == 'unavailable' and 'current_not_analysed' in i['reasonCodes'] for i in data['items'][5:])
    assert _dump(factory) == before


def test_missing_bound_report_never_falls_back_to_latest(synthetic_api):
    client, factory, ids = synthetic_api
    _saved(client, ids)
    original = client.get('/api/v1/career-agent/runs/update_source/result').json()
    report_id = original['bindings'][0]['matchReportId']
    with factory.begin() as session:
        session.execute(delete(MatchReportORM).where(MatchReportORM.id == report_id))
    before = _dump(factory)
    data = client.get(URL).json()
    assert data['items'][0]['previousReportId'] == report_id
    assert data['items'][0]['signal'] == 'unavailable'
    assert 'historical_report_missing' in data['items'][0]['reasonCodes']
    assert not data['rankingComparable'] and _dump(factory) == before


@pytest.mark.parametrize('mode,expected', [('improved','improved'), ('weakened','weakened'), ('mixed','mixed'), ('policy','not_comparable'), ('requirements','not_comparable')])
def test_synthetic_snapshot_judgment_directions_and_comparability(synthetic_api, mode, expected):
    client, factory, ids = synthetic_api
    _saved(client, ids)
    previous, current = SqlAlchemyAnalysisComparisonReader(factory).read('updated')
    binding = current.result.bindings[0]
    old = previous.reports[previous.result.bindings[0].match_report_id]
    new = current.reports[binding.match_report_id]
    if mode in ('improved','mixed'):
        old = replace(old, report=replace(old.report, recommendation=MatchRecommendation.STRETCH))
    if mode in ('weakened','mixed'):
        new = replace(new, report=replace(new.report, requirement_results=tuple(replace(r,
            semantic_verdict=SemanticMatchVerdict.NOT_MATCHED, eligibility_status=RequirementFitStatus.CONDITIONAL,
            evidence_ids=(), reason='Synthetic unverified, not inability') for r in new.report.requirement_results)))
    if mode == 'policy':
        new = replace(new, report=replace(new.report, policy_version='synthetic-next-policy'))
        current = replace(current, result=replace(current.result, bindings=(replace(binding, policy_version=new.report.policy_version), *current.result.bindings[1:])))
    if mode == 'requirements':
        new = replace(new, report=replace(new.report, requirement_results=tuple(replace(r, original_text='Changed saved requirement') for r in new.report.requirement_results)))
    previous = replace(previous, reports={**previous.reports, old.id: old})
    current = replace(current, reports={**current.reports, new.id: new})
    reader = Mock(); reader.read.return_value = previous, current
    result = CompareSavedAnalysesUseCase(reader).execute(thread_id='updated')
    assert result.items[0].signal == expected
    if expected == 'not_comparable':
        assert not result.ranking_comparable and all(i.rank_change is None for i in result.items)
    if mode == 'weakened':
        assert all(r.current_coverage == 'unverified' for r in result.items[0].requirements)


@pytest.mark.parametrize('mutation', ['report_identity', 'source', 'rank', 'scope'])
def test_corrupt_saved_references_rejected_instead_of_comparing_wrong_history(synthetic_api, mutation):
    client, factory, ids = synthetic_api
    _saved(client, ids)
    previous, current = SqlAlchemyAnalysisComparisonReader(factory).read('updated')
    if mutation == 'report_identity':
        key = current.result.bindings[0].match_report_id
        stored = current.reports[key]
        current = replace(current, reports={**current.reports, key: replace(stored, report=replace(stored.report, profile_version=999))})
    elif mutation == 'source': current = replace(current, state=replace(current.state, update_source_result_id='wrong'))
    elif mutation == 'rank': current = replace(current, state=replace(current.state, ranked_job_ids=()))
    else: current = replace(current, state=replace(current.state, requested_job_ids=tuple(ids[:7])))
    reader = Mock(); reader.read.return_value = previous, current
    with pytest.raises(AnalysisComparisonError): CompareSavedAnalysesUseCase(reader).execute(thread_id='updated')


def test_safe_http_errors_and_contract_sync(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    assert client.get(URL).status_code == 404
    state, _ = _begin(client, ids)
    assert client.get(URL).status_code == 409
    assert client.get('/api/v1/career-agent/runs/update_source/comparison').json()['error']['code'] == 'analysis_comparison_not_update'
    def fail(*args, **kwargs): raise OperationalError('PRIVATE SQL', {}, Exception('secret'))
    monkeypatch.setattr(SqlAlchemyAnalysisComparisonReader, 'read', fail)
    error = client.get(URL)
    assert error.status_code == 503 and error.json()['error']['retryable']
    assert 'PRIVATE' not in error.text and 'secret' not in error.text
    from app.api.v1.schemas.analysis_comparison import AnalysisComparisonResponse
    schema = json.loads((Path(__file__).parents[3] / 'packages/contracts/schemas/analysis-comparison.schema.json').read_text())
    del schema['$schema'], schema['$id']
    assert schema == AnalysisComparisonResponse.model_json_schema(by_alias=True)
