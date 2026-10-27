"""Compare explicitly saved reports, not current facts or inferred predecessors."""
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from app.agent.graph.state import CareerAgentState
from app.application.saved_career_analysis import SavedCareerAnalysis
from app.application.match_report import StoredMatchReport, MatchRecommendation, MatchReportRequirementResult
from app.application.eligibility import RequirementFitStatus
from app.application.semantic_match import SemanticMatchVerdict

Change = Literal['improved', 'weakened', 'unchanged', 'mixed', 'not_comparable', 'unavailable']


class AnalysisComparisonError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SavedComparisonSide:
    state: CareerAgentState
    result: SavedCareerAnalysis
    reports: dict[str, StoredMatchReport]


@dataclass(frozen=True)
class RequirementChange:
    requirement_id: str
    original_text: str
    previous_coverage: str
    current_coverage: str
    previous_reason: str
    current_reason: str
    previous_evidence_ids: tuple[str, ...]
    current_evidence_ids: tuple[str, ...]
    previous_fact_refs: tuple[str, ...]
    current_fact_refs: tuple[str, ...]
    change: Change


@dataclass(frozen=True)
class PreferenceChange:
    key: str
    previous_status: str | None
    current_status: str | None
    previous_code: str | None
    current_code: str | None
    previous_reason: str | None
    current_reason: str | None


@dataclass(frozen=True)
class AnalysisJobComparison:
    job_id: str
    title: str
    previous_report_id: str | None
    current_report_id: str | None
    previous_extraction_id: str | None
    current_extraction_id: str | None
    previous_policy_version: str | None
    current_policy_version: str | None
    previous_recommendation: str | None
    current_recommendation: str | None
    previous_rank: int | None
    current_rank: int | None
    rank_change: int | None
    signal: Change
    recommendation_change: Change
    coverage_change: Change
    reason_codes: tuple[str, ...]
    requirements: tuple[RequirementChange, ...]
    preferences: tuple[PreferenceChange, ...]


@dataclass(frozen=True)
class AnalysisComparison:
    comparison_version: Literal[1]
    source_thread_id: str
    source_result_id: str
    thread_id: str
    result_id: str
    scope: Literal['targets', 'batch']
    previous_profile_version: int
    current_profile_version: int
    previous_intent_version: int
    current_intent_version: int
    requested_job_ids: tuple[str, ...]
    ranking_comparable: bool
    partial: bool
    reason_codes: tuple[str, ...]
    added_target_ids: tuple[str, ...]
    removed_target_ids: tuple[str, ...]
    items: tuple[AnalysisJobComparison, ...]


class ComparisonReader(Protocol):
    def read(self, thread_id: str) -> tuple[SavedComparisonSide, SavedComparisonSide]: ...


_RECOMMENDATION = {MatchRecommendation.BLOCKED: 0, MatchRecommendation.LOW: 1,
                   MatchRecommendation.STRETCH: 2, MatchRecommendation.GOOD: 3, MatchRecommendation.STRONG: 4}
_COVERAGE = {'hard_conflict': 0, 'unverified': 1, 'partial': 2, 'supported': 3}


def _direction(delta) -> Change:
    return 'improved' if delta > 0 else 'weakened' if delta < 0 else 'unchanged'


def _coverage(r: MatchReportRequirementResult):
    if r.eligibility_status is RequirementFitStatus.MISSING:
        return 'hard_conflict'
    if r.semantic_verdict is SemanticMatchVerdict.MATCHED:
        return 'supported'
    if r.semantic_verdict is SemanticMatchVerdict.PARTIAL:
        return 'partial'
    return 'unverified'


def _combine(changes) -> Change:
    directions = set(changes) - {'unchanged'}
    if 'mixed' in directions or {'improved', 'weakened'} <= directions:
        return 'mixed'
    return next(iter(directions)) if directions else 'unchanged'


def _bound_reports(side):
    """Validate references against their own immutable result, not today's Profile."""
    found = {}
    bindings = {b.job_id: b for b in side.result.bindings}
    if (len(bindings) != len(side.result.bindings)
        or len(set(side.state.ranked_job_ids)) != len(side.state.ranked_job_ids)
        or set(bindings) != set(side.state.ranked_job_ids)
        or not set(bindings) <= set(side.state.requested_job_ids)
        or not set(side.result.inputs.selected_job_ids) <= set(bindings)
        or tuple(b.match_report_id for b in side.result.bindings) != side.result.inputs.match_report_ids):
        raise AnalysisComparisonError('analysis_comparison_binding_invalid')
    for job_id, binding in bindings.items():
        stored = side.reports.get(binding.match_report_id)
        if stored is None:
            continue
        report, inputs = stored.report, side.result.inputs
        if binding.match_report_id not in inputs.match_report_ids or (stored.id, report.job_id,
            report.extraction_id, report.policy_version, report.profile_id, report.profile_version,
            report.search_intent_id, report.search_intent_version) != (
            binding.match_report_id, job_id, binding.extraction_id, binding.policy_version,
            inputs.profile_id, inputs.profile_version, inputs.search_intent_id, inputs.search_intent_version):
            raise AnalysisComparisonError('analysis_comparison_binding_invalid')
        found[job_id] = stored
    return bindings, found


class CompareSavedAnalysesUseCase:
    def __init__(self, reader: ComparisonReader):
        self.reader = reader

    def execute(self, *, thread_id: str) -> AnalysisComparison:
        previous, current = self.reader.read(thread_id)
        old_state, state = previous.state, current.state
        old, new = previous.result, current.result
        for side in (previous, current):
            s, r = side.state, side.result
            if (s.thread_id, s.run_id, s.result_id, s.profile_id, s.profile_version,
                s.search_intent_id, s.search_intent_version, s.current_match_report_ids,
                s.confirmed_target_job_ids) != (r.thread_id, r.run_id, r.result_id, r.inputs.profile_id,
                r.inputs.profile_version, r.inputs.search_intent_id, r.inputs.search_intent_version,
                r.inputs.match_report_ids, r.inputs.selected_job_ids):
                raise AnalysisComparisonError('analysis_comparison_binding_invalid')
        if (state.update_source_thread_id, state.update_source_result_id) != (old.thread_id, old.result_id):
            raise AnalysisComparisonError('analysis_comparison_binding_invalid')
        scope = old.inputs.selected_job_ids if state.update_scope == 'targets' else old_state.requested_job_ids
        if state.update_scope not in ('targets', 'batch') or not 1 <= len(scope) <= 50 or tuple(scope) != state.requested_job_ids:
            raise AnalysisComparisonError('analysis_comparison_scope_invalid')
        old_bindings, old_reports = _bound_reports(previous)
        new_bindings, new_reports = _bound_reports(current)
        scope_set = set(scope)
        old_rank = tuple(j for j in old_state.ranked_job_ids if j in scope_set)
        new_rank = tuple(j for j in state.ranked_job_ids if j in scope_set)
        context_reasons = []
        if (old.inputs.profile_id, old.inputs.profile_version) != (new.inputs.profile_id, new.inputs.profile_version):
            context_reasons.append('profile_changed')
        if (old.inputs.search_intent_id, old.inputs.search_intent_version) != (new.inputs.search_intent_id, new.inputs.search_intent_version):
            context_reasons.append('intent_changed')
        if old.inputs.selected_job_ids != new.inputs.selected_job_ids:
            context_reasons.append('targets_changed')
        comparable = not state.update_partial and set(old_rank) == set(new_rank) and bool(old_rank)
        comparable = comparable and all(j in old_reports and j in new_reports and
            (old_reports[j].report.extraction_id, old_reports[j].report.policy_version) ==
            (new_reports[j].report.extraction_id, new_reports[j].report.policy_version) for j in scope)
        if not comparable:
            context_reasons.append('ranking_scope_not_comparable')
        items = []
        for job_id in scope:
            before, after = old_reports.get(job_id), new_reports.get(job_id)
            b, a = old_bindings.get(job_id), new_bindings.get(job_id)
            reasons, requirements, preferences = [], (), ()
            signal: Change = 'unavailable'
            recommendation_change: Change = 'unavailable'
            coverage_change: Change = 'unavailable'
            if after is None:
                reasons.append('current_not_analysed' if a is None else 'current_report_missing')
            if before is None:
                reasons.append('historical_not_saved' if b is None else 'historical_report_missing')
            if before and after:
                br, ar = before.report, after.report
                if br.extraction_id != ar.extraction_id: reasons.append('requirements_changed')
                if br.policy_version != ar.policy_version: reasons.append('policy_changed')
                if (br.matcher_version, br.prompt_version, br.model) != (ar.matcher_version, ar.prompt_version, ar.model):
                    reasons.append('judgment_method_changed')
                old_requirements = {r.requirement_id: r for r in br.requirement_results}
                new_requirements = {r.requirement_id: r for r in ar.requirement_results}
                if set(old_requirements) != set(new_requirements) or len(old_requirements) != len(br.requirement_results) or len(new_requirements) != len(ar.requirement_results):
                    reasons.append('requirement_snapshot_mismatch')
                elif any((r.original_text, r.type, r.importance, r.normalized_capability) != (
                    new_requirements[k].original_text, new_requirements[k].type,
                    new_requirements[k].importance, new_requirements[k].normalized_capability) for k, r in old_requirements.items()):
                    reasons.append('requirement_snapshot_mismatch')
                old_preferences, new_preferences = {p.key: p for p in br.preference_checks}, {p.key: p for p in ar.preference_checks}
                preferences = tuple(PreferenceChange(key,
                    old_preferences[key].status.value if key in old_preferences else None,
                    new_preferences[key].status.value if key in new_preferences else None,
                    old_preferences[key].code if key in old_preferences else None,
                    new_preferences[key].code if key in new_preferences else None,
                    old_preferences[key].reason if key in old_preferences else None,
                    new_preferences[key].reason if key in new_preferences else None)
                    for key in dict.fromkeys((*old_preferences, *new_preferences)))
                if any((p.previous_status, p.previous_code) != (p.current_status, p.current_code) for p in preferences):
                    reasons.append('preference_judgment_changed')
                if any(code in reasons for code in ('requirements_changed', 'policy_changed', 'requirement_snapshot_mismatch')):
                    signal = recommendation_change = coverage_change = 'not_comparable'
                else:
                    requirements = tuple(RequirementChange(k, r.original_text, _coverage(r), _coverage(new_requirements[k]),
                        r.reason, new_requirements[k].reason, r.evidence_ids, new_requirements[k].evidence_ids,
                        r.profile_fact_refs, new_requirements[k].profile_fact_refs,
                        _direction(_COVERAGE[_coverage(new_requirements[k])] - _COVERAGE[_coverage(r)]))
                        for k, r in old_requirements.items())
                    recommendation_change = _direction(_RECOMMENDATION[ar.recommendation] - _RECOMMENDATION[br.recommendation])
                    coverage_change = _combine(r.change for r in requirements)
                    signal = _combine((recommendation_change, coverage_change))
                    reasons.append(f'conclusion_{signal}')
                    if any((r.previous_evidence_ids, r.previous_fact_refs) != (r.current_evidence_ids, r.current_fact_refs) for r in requirements):
                        reasons.append('evidence_references_changed')
            previous_rank = old_rank.index(job_id) + 1 if job_id in old_rank else None
            current_rank = new_rank.index(job_id) + 1 if job_id in new_rank else None
            items.append(AnalysisJobComparison(job_id, a.title if a else b.title if b else job_id,
                before.id if before else b.match_report_id if b else None, after.id if after else a.match_report_id if a else None,
                b.extraction_id if b else None, a.extraction_id if a else None, b.policy_version if b else None, a.policy_version if a else None,
                before.report.recommendation.value if before else None, after.report.recommendation.value if after else None,
                previous_rank, current_rank, previous_rank-current_rank if comparable and previous_rank and current_rank else None,
                signal, recommendation_change, coverage_change, tuple(reasons), requirements, preferences))
        if comparable and any(item.signal in {'not_comparable', 'unavailable'} for item in items):
            comparable = False
            context_reasons.append('ranking_scope_not_comparable')
            items = [replace(item, rank_change=None) for item in items]
        return AnalysisComparison(1, old.thread_id, old.result_id, new.thread_id, new.result_id, state.update_scope,
            old.inputs.profile_version, new.inputs.profile_version, old.inputs.search_intent_version, new.inputs.search_intent_version,
            tuple(scope), comparable, state.update_partial, tuple(context_reasons),
            tuple(j for j in new.inputs.selected_job_ids if j not in old.inputs.selected_job_ids),
            tuple(j for j in old.inputs.selected_job_ids if j not in new.inputs.selected_job_ids), tuple(items))
