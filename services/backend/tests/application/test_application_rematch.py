from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.application.application_workspace.evidence_proposal import EvidenceProposal, EvidenceProposalStatus
from app.application.application_workspace.models import ApplicationWorkspace, ApplicationWorkspaceSourceSnapshot, ApplicationWorkspaceStatus
from app.application.application_workspace.rematch import ApplicationRematchBlockedError, RematchRankingSignal, RunApplicationRematchUseCase
from app.application.eligibility import EligibilityDecision, JobEligibilityResult, RequirementEligibilityResult, RequirementFitStatus
from app.application.evidence_retrieval.models import CandidateEvidence, EvidenceRelevanceTier, EvidenceRetrievalBasis, JobEvidenceRetrievalResult, RequirementEvidenceCandidates
from app.application.match_improvement import MatchImprovement
from app.application.match_report import MatchRecommendation
from app.domain.career_context import EvidenceType, SkillLevel
from app.domain.job_requirements import RequirementImportance, RequirementType

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def _workspace():
    return ApplicationWorkspace("ws1", "job1", "user1", "wk", ApplicationWorkspaceStatus.PREPARING, ApplicationWorkspaceSourceSnapshot("p1", 3, "s1", 1, "rx1", "old-report"), "f" * 64, NOW, NOW)


def _proposal():
    return EvidenceProposal("ep1", "ws1", "a1", "user1", "pk", EvidenceProposalStatus.CONFIRMED, ("req1",), "LangGraph", EvidenceType.PROJECT, "真实经历", "repo", SkillLevel.WORKING, "p1", 3, NOW, "p1", 4, NOW)


class Workspaces:
    def get(self, workspace_id): return _workspace() if workspace_id == "ws1" else None


class Proposals:
    def get(self, proposal_id): return _proposal() if proposal_id == "ep1" else None


class Timeline:
    def __init__(self): self.items = []
    def get_by_actor_and_idempotency_key(self, actor_id, key): return next((x for x in self.items if x.actor_id == actor_id and x.idempotency_key == key), None)
    def add(self, event): self.items.append(event); return event


def _eligibility(status=RequirementFitStatus.MATCHED):
    item = RequirementEligibilityResult("req1", 0, RequirementType.SKILL, RequirementImportance.MUST_HAVE, "LangGraph", "LangGraph", status, ("ev-new",) if status is RequirementFitStatus.MATCHED else (), (), "deterministic")
    return JobEligibilityResult("job1", "p1", 4, "rx1", EligibilityDecision.ELIGIBLE, (item,), int(status is RequirementFitStatus.MATCHED), int(status is RequirementFitStatus.CONDITIONAL), int(status is RequirementFitStatus.MISSING))


class Eligibility:
    def __init__(self, result): self.result = result
    def execute(self, job_id): return self.result


def _retrieval(with_candidate=False):
    candidate = CandidateEvidence("ev-new", "ev-key", EvidenceType.PROJECT, "真实经历", "repo", EvidenceRelevanceTier.DIRECT, EvidenceRetrievalBasis.EXACT_SKILL_LINK, ("LangGraph",), "exact skill")
    requirement = RequirementEvidenceCandidates("req1", 0, RequirementType.SKILL, RequirementImportance.MUST_HAVE, "LangGraph", "LangGraph", (candidate,) if with_candidate else ())
    return JobEvidenceRetrievalResult("job1", "p1", 4, "rx1", (requirement,), int(with_candidate))


class Evidence:
    def __init__(self, result): self.result = result
    def execute(self, job_id): return self.result


class Reports:
    def __init__(self): self.items = []
    def list_for_job(self, job_id): return tuple(self.items)


class Runner:
    def __init__(self, reports): self.reports = reports; self.calls = 0
    def execute(self, job_id):
        self.calls += 1
        report = SimpleNamespace(profile_version=4, extraction_id="rx1", recommendation=MatchRecommendation.GOOD, provider_calls=0)
        self.reports.items.insert(0, SimpleNamespace(id="new-report", report=report))
        return report


class Improvement:
    def execute(self, *, job_id, current_report_id):
        return MatchImprovement(job_id, current_report_id, "old-report", MatchRecommendation.BLOCKED, MatchRecommendation.GOOD, 3, 4, 1, 0, ("req1",), (), (), (), (), True)


def _use_case(*, eligibility=None, evidence=None):
    reports = Reports(); timeline = Timeline(); runner = Runner(reports)
    use_case = RunApplicationRematchUseCase(
        workspaces=Workspaces(), proposals=Proposals(), timeline=timeline, reports=reports,
        eligibility=Eligibility(eligibility or _eligibility()), evidence=Evidence(evidence or _retrieval()),
        report_runner=runner, improvement=Improvement(), now=lambda: NOW, new_event_id=lambda: "evt1",
    )
    return use_case, runner, timeline


def test_confirmed_evidence_can_run_zero_provider_rematch_and_expose_ranking_signal():
    use_case, runner, timeline = _use_case()
    result = use_case.execute(workspace_id="ws1", proposal_id="ep1", actor_id="user1", idempotency_key="rematch-1")
    assert runner.calls == 1
    assert result.provider_calls == 0
    assert result.target_resolved_requirement_ids == ("req1",)
    assert result.previous_recommendation is MatchRecommendation.BLOCKED
    assert result.current_recommendation is MatchRecommendation.GOOD
    assert result.ranking_signal is RematchRankingSignal.IMPROVED
    assert timeline.items[0].event_type.value == "rematch_completed"


def test_rematch_fails_before_match_write_when_semantic_provider_would_be_required():
    use_case, runner, timeline = _use_case(
        eligibility=_eligibility(RequirementFitStatus.CONDITIONAL),
        evidence=_retrieval(with_candidate=True),
    )
    with pytest.raises(ApplicationRematchBlockedError, match="application_rematch_provider_required"):
        use_case.execute(workspace_id="ws1", proposal_id="ep1", actor_id="user1", idempotency_key="rematch-1")
    assert runner.calls == 0
    assert timeline.items == []
