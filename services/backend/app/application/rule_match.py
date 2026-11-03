"""Run the existing Match algorithms on captured facts with no provider capability."""
from app.application.eligibility import EligibilityDecision
from app.application.eligibility.use_case import evaluate_match_eligibility
from app.application.evidence_retrieval.retriever import retrieve_candidate_evidence
from app.application.semantic_match.call_boundary import needs_semantic_model
from app.application.match_report.builder import build_match_report
from app.application.match_report.use_case import _blocked_semantic_result
from app.workflows.semantic_match import SemanticMatchWorkflow


class RuleMatchRequiresModel(ValueError):
    pass


class _NoModel:
    def match(self, *args, **kwargs):
        raise AssertionError('Rule-only execution has no model authorization')

    @property
    def model_name(self):
        raise AssertionError('Rule-only execution cannot access a provider')


def _no_trace():
    raise AssertionError('Rule-only execution cannot create provider traces')


class BuildPinnedRuleMatch:
    def execute(self, *, profile, intent, job, extraction):
        eligibility = evaluate_match_eligibility(profile=profile, intent=intent, job=job, extraction=extraction)
        if eligibility.eligibility is EligibilityDecision.BLOCKED:
            return build_match_report(_blocked_semantic_result(eligibility))
        evidence = retrieve_candidate_evidence(profile=profile, extraction=extraction)
        candidates = {r.requirement_id: r.candidates for r in evidence.requirements}
        if any(needs_semantic_model(r.status, candidates.get(r.requirement_id, ())) for r in eligibility.requirements):
            raise RuleMatchRequiresModel('model_authorization_required')
        result = SemanticMatchWorkflow(matcher=_NoModel(), trace_uow_factory=_no_trace).execute(
            eligibility=eligibility, evidence=evidence)
        return build_match_report(result)
