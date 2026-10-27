"""Read-only plan for updating an original job scope, never an execution receipt."""
from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from typing import Literal
from urllib.parse import quote

from app.application.career_context.models import CareerContextSnapshot
from app.application.job_queries.models import JobDetail
from app.application.job_requirements.models import JobRequirementExtractionDetail
from app.application.match_report import StoredMatchReport
from app.application.match_report_history import report_stale_reasons
from app.application.eligibility.use_case import evaluate_match_eligibility
from app.application.eligibility import EligibilityDecision
from app.application.search_preferences import preference_input_fingerprint
from app.application.semantic_match.call_boundary import needs_semantic_model
from app.application.evidence_retrieval.retriever import retrieve_candidate_evidence

UpdateScope = Literal['targets', 'batch']


class UpdateMatchFactsChanged(ValueError):
    pass


class AnalysisUpdatePlanError(ValueError):
    pass


@dataclass(frozen=True)
class UpdateJobFacts:
    job_id: str
    job: JobDetail | None
    extraction: JobRequirementExtractionDetail | None
    latest_report: StoredMatchReport | None


@dataclass(frozen=True)
class UpdateFacts:
    thread_id: str
    result_id: str
    scope: UpdateScope
    previous_profile_version: int
    context: CareerContextSnapshot
    jobs: tuple[UpdateJobFacts, ...]


@dataclass(frozen=True)
class AnalysisUpdateItem:
    job_id: str
    title: str
    status: Literal['reuse', 'ready', 'deferred', 'requires_model', 'input_blocked']
    extraction_id: str | None
    reusable_report_id: str | None
    stale_reasons: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    required_operations: tuple[str, ...]
    repair_href: str
    input_fingerprint: str
    base_report_id: str | None


@dataclass(frozen=True)
class AnalysisUpdatePlan:
    source_thread_id: str
    source_result_id: str
    scope: UpdateScope
    previous_profile_version: int
    profile_id: str | None
    profile_version: int | None
    search_intent_id: str | None
    search_intent_version: int | None
    max_new_analyses: int
    items: tuple[AnalysisUpdateItem, ...]
    next_job_ids: tuple[str, ...]
    reusable_job_ids: tuple[str, ...]
    input_digest: str
    advisory_only: bool = True


class PlanAnalysisUpdateUseCase:
    MAX_NEW_ANALYSES = 5

    def __init__(self, *, reader, readiness):
        self._reader, self._readiness = reader, readiness

    def execute(self, *, thread_id: str, scope: UpdateScope = 'targets') -> AnalysisUpdatePlan:
        if scope not in ('targets', 'batch'):
            raise AnalysisUpdatePlanError('analysis_update_scope_invalid')
        facts = self._reader.read(thread_id, scope)
        if not 1 <= len(facts.jobs) <= 50:
            raise AnalysisUpdatePlanError('analysis_update_scope_invalid')
        profile, intent = facts.context.profile, facts.context.search_intent
        items, next_ids = [], []
        for item in facts.jobs:
            blockers = []
            operations = []
            stale = report_stale_reasons(item.latest_report.report, profile=profile, intent=intent,
                extraction=item.extraction, job=item.job) if item.latest_report else ('match_report_missing',)
            if item.job is None:
                blockers.append('job_missing')
            if profile is None:
                blockers.append('profile_missing')
            if intent is None:
                blockers.append('search_intent_missing')
            if item.extraction is None:
                blockers.append('requirements_missing')
                operations.append('extract_requirements')
            if item.job is not None:
                ready = self._readiness.execute(item.job_id)
                blockers.extend(str(getattr(b.code, 'value', b.code)) for b in ready.blockers)
                if ready.inputs_release_eligible and profile and intent and item.extraction:
                    if (ready.career_context.profile_id, ready.career_context.profile_version,
                        ready.career_context.search_intent_id, ready.career_context.search_intent_version,
                        ready.job_requirements.extraction_id) != (profile.id, profile.version,
                        intent.id, intent.version, item.extraction.extraction_id):
                        blockers.append('update_inputs_changed')
            status = 'input_blocked'
            reusable = None
            if not blockers:
                if not stale:
                    status, reusable = 'reuse', item.latest_report.id
                else:
                    # These are existing deterministic algorithms, not a model verdict or Match write.
                    eligibility = evaluate_match_eligibility(profile=profile, extraction=item.extraction, intent=intent, job=item.job)
                    evidence = retrieve_candidate_evidence(profile=profile, extraction=item.extraction)
                    candidates = {r.requirement_id: r.candidates for r in evidence.requirements}
                    needs_model = eligibility.eligibility is not EligibilityDecision.BLOCKED and any(needs_semantic_model(r.status, candidates.get(r.requirement_id, ()))
                        for r in eligibility.requirements)
                    if needs_model:
                        status = 'requires_model'
                        operations.append('semantic_match')
                        blockers.append('model_authorization_required')
                    elif len(next_ids) < self.MAX_NEW_ANALYSES:
                        status = 'ready'
                        next_ids.append(item.job_id)
                    else:
                        status = 'deferred'
            href = '/profile' if any(b.startswith(('profile_', 'search_intent_')) for b in blockers) else f'/jobs/{quote(item.job_id, safe="")}'
            items.append(AnalysisUpdateItem(item.job_id, item.job.title if item.job else item.job_id,
                status, item.extraction.extraction_id if item.extraction else None, reusable,
                stale, tuple(dict.fromkeys(blockers)), tuple(operations), href,
                preference_input_fingerprint(intent, item.job) if intent and item.job else "missing",
                item.latest_report.id if item.latest_report else None))
        digest = sha256(json.dumps(dict(source=facts.thread_id, result=facts.result_id, scope=scope,
            profile=(profile.id, profile.version) if profile else None,
            intent=(intent.id, intent.version) if intent else None,
            items=[asdict(i) for i in items]), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return AnalysisUpdatePlan(facts.thread_id, facts.result_id, facts.scope, facts.previous_profile_version,
            profile.id if profile else None, profile.version if profile else None,
            intent.id if intent else None, intent.version if intent else None,
            self.MAX_NEW_ANALYSES, tuple(items), tuple(next_ids),
            tuple(i.job_id for i in items if i.status == 'reuse'), digest)
