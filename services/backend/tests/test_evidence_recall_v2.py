"""Expression differences must retrieve candidates, never manufacture capability facts."""
from dataclasses import replace
import pytest
from app.application.evidence_retrieval import retrieve_candidate_evidence, EvidenceRelevanceTier
from app.application.evidence_retrieval.strategy import RETRIEVAL_VERSION
from .test_evidence_retrieval import _profile, _requirement, _extraction
from .test_match_report_repository import _report, _factory
from app.repositories.sqlalchemy_match_report_unit_of_work import SqlAlchemyMatchReportUnitOfWork
from app.repositories.sqlalchemy_match_report_repository import SqlAlchemyMatchReportQueryRepository
from sqlalchemy import text


def retrieve(text, profile=None, capability=None):
    return retrieve_candidate_evidence(profile=profile or _profile(), extraction=_extraction(
        _requirement(0, text=text, capability=capability)))


def test_long_responsibility_with_explicit_technology_retrieves_confirmed_evidence():
    result = retrieve('具备 TypeScript 与任一现代框架经验，能独立完成交付。')
    assert [c.evidence_id for c in result.requirements[0].candidates] == ['ev_frontend']
    assert result.requirements[0].candidates[0].relevance_tier is EvidenceRelevanceTier.DIRECT
    assert (result.db_writes, result.provider_calls, result.trace_runs_created) == (0, 0, 0)


def test_concrete_cross_platform_responsibility_retrieves_related_not_matched():
    result = retrieve('负责 PC 客户端、移动端与 Web 端，主导客户端重构。')
    candidates = result.requirements[0].candidates
    assert [c.evidence_id for c in candidates] == ['ev_frontend']
    assert candidates[0].relevance_tier is EvidenceRelevanceTier.RELATED
    assert candidates[0].matched_terms


@pytest.mark.parametrize('requirement,summary', [
    ('精通 Java', '使用 JavaScript 构建界面'),
    ('Java', 'JavaScript'),
    ('React', 'reactive'),
    ('开发', '负责产品开发'),
    ('熟悉 React', 'Implemented reactive data flows'),
    ('负责产品开发与系统工作', '参与系统产品开发'),
    ('熟悉量子计算', '负责前端组件库与交付'),
])
def test_no_generic_word_or_english_substring_recall(requirement, summary):
    p = _profile()
    p = replace(p, skills=(), evidence=(replace(p.evidence[0], summary=summary),))
    assert retrieve(requirement, p).candidate_count == 0


def test_cap_dedup_and_order_do_not_depend_on_profile_list_order():
    p = _profile()
    evidence = tuple(replace(p.evidence[0], id=f'ev_{i}', summary='使用 TypeScript 开发服务') for i in range(6))
    p = replace(p, skills=(), evidence=evidence)
    first = retrieve('熟悉 TypeScript', p)
    second = retrieve('熟悉 TypeScript', replace(p, evidence=tuple(reversed(evidence))))
    assert [c.evidence_id for c in first.requirements[0].candidates] == ['ev_0', 'ev_1', 'ev_2']
    assert first == second


def test_new_metadata_roundtrips_and_missing_historical_metadata_stays_unknown(tmp_path):
    factory = _factory(tmp_path)
    original = _report()
    report = replace(original, retrieval_version=RETRIEVAL_VERSION, requirement_results=(
        replace(original.requirement_results[0], candidate_count=2, assessment_source='provider'),))
    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        saved = uow.reports.add(report); uow.commit()
    repo = SqlAlchemyMatchReportQueryRepository(factory)
    assert repo.get(saved.id).report.retrieval_version == RETRIEVAL_VERSION
    assert repo.get(saved.id).report.requirement_results[0].candidate_count == 2
    # Simulate an old, immutable JSON format, not a new interpretation of its result.
    import json
    with factory.begin() as session:
        snapshot = json.loads(session.execute(text('select snapshot from match_reports where id=:id'), {'id':saved.id}).scalar_one())
        snapshot.pop('retrievalVersion')
        for item in snapshot['requirementResults']:
            item.pop('candidateCount'); item.pop('assessmentSource')
        session.execute(text('update match_reports set snapshot=:s where id=:id'), {'id':saved.id,'s':json.dumps(snapshot)})
    restored = repo.get(saved.id).report
    assert restored.retrieval_version is None
    assert restored.requirement_results[0].candidate_count is None
    assert restored.requirement_results[0].assessment_source is None
    assert restored.summary == original.summary


def test_old_retrieval_version_is_stale_without_rewriting_report():
    from app.application.match_report_history import report_stale_reasons
    original = _report()
    stale = report_stale_reasons(replace(original, retrieval_version=None), profile=None, intent=None, extraction=None, job=None)
    assert 'retrieval_changed' in stale
    assert original.summary == _report().summary



def test_thirteen_unknown_requirements_do_not_invoke_model_or_omit_results():
    from unittest.mock import Mock
    from .test_semantic_match_workflow import _eligibility, _related_retrieval
    from app.application.eligibility import RequirementFitStatus, EligibilityDecision
    from app.workflows.semantic_match import SemanticMatchWorkflow
    from app.application.match_report.builder import build_match_report
    e = _eligibility(status=RequirementFitStatus.CONDITIONAL, overall=EligibilityDecision.CONDITIONAL)
    r = _related_retrieval()
    eligibility = replace(e, requirements=tuple(replace(e.requirements[0], requirement_id=f'r{i}', requirement_index=i) for i in range(13)))
    retrieval = replace(r, candidate_count=0, requirements=tuple(replace(r.requirements[0], requirement_id=f'r{i}', requirement_index=i, candidates=()) for i in range(13)))
    matcher = Mock(side_effect=AssertionError('No candidate may dispatch a model'))
    trace = Mock(side_effect=AssertionError('No model trace without a call'))
    result = SemanticMatchWorkflow(matcher=matcher, trace_uow_factory=trace).execute(eligibility=eligibility, evidence=retrieval)
    report = build_match_report(result)
    assert len(report.requirement_results) == 13 and report.provider_calls == 0
    assert report.retrieval_version == RETRIEVAL_VERSION
    assert all(r.candidate_count == 0 and r.assessment_source == 'deterministic' for r in report.requirement_results)
    assert '已提取 13 条要求' in report.summary and '本次未进行语义判断' in report.summary
    assert not matcher.called and not trace.called


def test_shared_schema_accepts_new_and_unknown_legacy_metadata():
    import json
    from pathlib import Path
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from app.api.v1.schemas.match_report import JobMatchReportResponse
    root = Path(__file__).resolve().parents[3] / 'packages/contracts/schemas'
    documents = [json.loads(p.read_text()) for p in root.glob('*.json')]
    registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in documents if '$id' in s)
    schema = json.loads((root / 'match-report.schema.json').read_text())
    original = _report()
    report = replace(original, retrieval_version=RETRIEVAL_VERSION, requirement_results=(
        replace(original.requirement_results[0], candidate_count=1, assessment_source='provider'),))
    data = JobMatchReportResponse.from_detail(report).model_dump(mode='json', by_alias=True)
    validator = Draft202012Validator(schema, registry=registry)
    validator.validate(data)
    data.pop('retrievalVersion')
    for item in data['requirementResults']:
        item.pop('candidateCount'); item.pop('assessmentSource')
    validator.validate(data)
