"""Explicit one-job semantic command, frozen facts, existing workflow and report builder."""
from app.application.evidence_retrieval.strategy import RETRIEVAL_VERSION
import json
from dataclasses import asdict
from hashlib import sha256
from types import SimpleNamespace
from app.application.job_requirements.call_models import RequirementCallConflict, digest
from app.application.eligibility import EligibilityDecision
from app.application.job_queries.errors import JobNotFoundError
from app.application.semantic_match.call_boundary import needs_semantic_model, semantic_requirement_input, semantic_input_payload
from app.application.match_policy_version import CURRENT_MATCH_POLICY_VERSION
from app.application.match_report import BuildJobMatchReportUseCase
from app.workflows.semantic_match import SemanticMatchWorkflow, MATCHER_VERSION, PROMPT_VERSION


class AuthorizedSemanticMatch:
    def __init__(self, *, settings, eligibility, evidence, jobs, journal, uow_factory, traces, matcher_factory):
        self.settings, self.eligibility, self.evidence, self.jobs = settings, eligibility, evidence, jobs
        self.journal, self.uow_factory, self.traces, self.matcher_factory = journal, uow_factory, traces, matcher_factory

    def plan(self, job_id):
        job = self.jobs.get_job(job_id)
        if job is None:
            raise JobNotFoundError("Job not found")
        # Both runners are read-only; the workflow also checks their frozen identities.
        eligibility, evidence = self.eligibility.execute(job_id), self.evidence.execute(job_id)
        SemanticMatchWorkflow._validate_input_identity(eligibility=eligibility, evidence=evidence)
        candidates = {item.requirement_id: item.candidates for item in evidence.requirements}
        preview = []
        model_inputs = []
        if eligibility.eligibility is not EligibilityDecision.BLOCKED:
            for item in eligibility.requirements:
                selected = candidates[item.requirement_id]
                if needs_semantic_model(item.status, selected):
                    model_inputs.append(semantic_requirement_input(item, selected))
                    preview.append(dict(requirementId=item.requirement_id, requirementText=item.original_text,
                        candidates=[dict(evidenceId=c.evidence_id, summary=c.summary) for c in selected]))
        s = self.settings
        snapshot = dict(connectionVersion=getattr(self.settings, "byok_connection_version", ""), jobId=job_id, inputHash=sha256((job.description or "").strip().encode()).hexdigest(),
            availabilityRevision=job.availability_revision, previousExtractionId=eligibility.extraction_id,
            profileId=eligibility.profile_id, profileVersion=eligibility.profile_version,
            searchIntentId=eligibility.search_intent_id, searchIntentVersion=eligibility.search_intent_version,
            factsDigest=digest([asdict(eligibility), asdict(evidence)]),
            policy=[CURRENT_MATCH_POLICY_VERSION, MATCHER_VERSION, PROMPT_VERSION, RETRIEVAL_VERSION], model=s.semantic_match_model.strip(),
            maxOutputTokens=min(4096, max(256, s.semantic_match_max_completion_tokens or 4096)),
            timeoutSeconds=min(60., max(1., s.semantic_match_timeout_seconds)),
            configuration=digest(dict(provider=s.semantic_match_provider, model=s.semantic_match_model,
                url=s.openai_base_url, style=s.semantic_match_api_style, thinking=s.semantic_match_enable_thinking)))
        blocked = None
        if not preview:
            blocked = "semantic_model_not_needed"
        elif s.semantic_match_provider.strip().casefold() != "openai" or not s.openai_api_key or not snapshot["model"]:
            blocked = "live_provider_not_configured"
        elif len(json.dumps(semantic_input_payload(tuple(model_inputs)), ensure_ascii=False)) > 12000 or len(preview) > 50:
            blocked = "semantic_input_outside_call_limit"
        return dict(executionMode="offline" if s.semantic_match_provider.strip().casefold() == "fixture" else "authorized",
            jobId=job_id, planDigest=digest(snapshot), available=blocked is None, blockerCode=blocked,
            model=snapshot["model"], maxProviderCalls=1, maxOutputTokens=snapshot["maxOutputTokens"],
            timeoutSeconds=snapshot["timeoutSeconds"], profileVersion=eligibility.profile_version,
            searchIntentVersion=eligibility.search_intent_version, extractionId=eligibility.extraction_id,
            requirements=preview, latestRequest=self.journal.get(job_id)), snapshot, eligibility, evidence

    def execute(self, job_id, command):
        old = self.journal.get(job_id, command.action_id)
        content = command.model_dump(mode="json", by_alias=True)
        # Completed/failed/uncertain commands replay even if current facts no longer pass readiness.
        if old:
            return self.journal.reserve(job_id=job_id, action_id=command.action_id, command=content,
                snapshot={}, acknowledged=command.acknowledged_prior_request_id)[0]
        public, snapshot, eligibility, evidence = self.plan(job_id)
        if not command.confirmed or command.max_provider_calls != 1:
            raise RequirementCallConflict("model_authorization_required")
        if command.plan_digest != public["planDigest"]:
            raise RequirementCallConflict("match_plan_stale")
        if not public["available"]:
            raise RequirementCallConflict(public["blockerCode"])
        record, claimed = self.journal.reserve(job_id=job_id, action_id=command.action_id, command=content,
            snapshot=snapshot, acknowledged=command.acknowledged_prior_request_id)
        if not claimed:
            return record
        try:
            with self.matcher_factory(command.action_id, snapshot) as matcher:
                workflow = SemanticMatchWorkflow(matcher=matcher, trace_uow_factory=self.traces)
                runner = SimpleNamespace(execute=lambda _: workflow.execute(eligibility=eligibility, evidence=evidence))
                BuildJobMatchReportUseCase(runner, eligibility=SimpleNamespace(execute=lambda _: eligibility),
                    jobs=self.jobs, uow_factory=lambda: self.uow_factory(command.action_id)).execute(job_id)
        except Exception as exc:
            # Never persist exception text: the provider could echo private evidence or credentials.
            code = "match_facts_changed" if isinstance(exc, RequirementCallConflict) else "semantic_result_not_saved"
            self.journal.fail(command.action_id, code)
        return self.journal.get(job_id, command.action_id)
