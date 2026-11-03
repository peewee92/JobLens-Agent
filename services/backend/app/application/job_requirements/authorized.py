"""One bounded user command reuses the existing extraction workflow and persistence."""
from hashlib import sha256
from app.application.job_queries.errors import JobNotFoundError
from app.application.job_requirements.use_cases import ExtractJobRequirementsUseCase
from app.workflows.job_requirement_extraction import ExtractJobRequirementsWorkflow, EXTRACTOR_VERSION, PROMPT_VERSION
from app.application.job_requirements.validation import SEMANTIC_POLICY_VERSION
from app.application.job_requirements.call_models import RequirementCallConflict, digest
from app.application.job_requirements.errors import (
    InvalidRequirementExtractorOutputError, RequirementExtractorUnavailableError,
    JobDescriptionChangedDuringExtractionError, RequirementExtractionSupersededError,
)


class AuthorizedRequirementExtraction:
    def __init__(self, *, settings, jobs, requirements, journal, uow_factory, traces, extractor_factory):
        self.settings, self.jobs, self.requirements = settings, jobs, requirements
        self.journal, self.uow_factory, self.traces = journal, uow_factory, traces
        self.extractor_factory = extractor_factory

    def plan(self, job_id):
        settings = self.settings
        job = self.jobs.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id!r} was not found")
        description = (job.description or "").strip()
        snapshot = dict(connectionVersion=getattr(self.settings, "byok_connection_version", ""), jobId=job_id, inputHash=sha256(description.encode()).hexdigest(),
            availabilityRevision=job.availability_revision,
            previousExtractionId=self.requirements.get_latest_id(job_id),
            extractionPolicy=[EXTRACTOR_VERSION, PROMPT_VERSION, SEMANTIC_POLICY_VERSION],
            model=settings.requirement_extractor_model.strip(),
            maxOutputTokens=min(4096, max(256, settings.requirement_extractor_max_completion_tokens or 4096)),
            timeoutSeconds=min(60.0, max(1.0, settings.requirement_extractor_timeout_seconds)),
            # Includes sensitive configuration only as a one-way fingerprint, never in responses/logs.
            configuration=digest(dict(provider=settings.requirement_extractor_provider,
                model=settings.requirement_extractor_model, url=settings.openai_base_url,
                style=settings.requirement_extractor_api_style, thinking=settings.requirement_extractor_enable_thinking)))
        blocked = None
        if settings.requirement_extractor_provider.strip().casefold() != "openai":
            blocked = "live_provider_not_configured"
        elif not settings.openai_api_key or not snapshot["model"]:
            blocked = "live_provider_not_configured"
        elif job.user_marked_inactive:
            blocked = "job_unavailable"
        elif len(description) < 40 or len(description) > 12000:
            blocked = "description_outside_call_limit"
        elif (job.source_version or "").startswith("1.4.") and job.requirement_review_eligible is not True:
            blocked = "description_not_extractable"
        public = dict(jobId=job_id, planDigest=digest(snapshot), inputHash=snapshot["inputHash"],
            available=blocked is None, blockerCode=blocked, model=snapshot["model"],
            maxProviderCalls=1, maxOutputTokens=snapshot["maxOutputTokens"],
            timeoutSeconds=snapshot["timeoutSeconds"], descriptionCharacters=len(description),
            latestRequest=self.journal.get(job_id))
        return public, snapshot

    def execute(self, job_id, command):
        # Replay does not re-evaluate configuration or initiate a second model call.
        old = self.journal.get(job_id, command.action_id)
        public, snapshot = self.plan(job_id)
        content = command.model_dump(mode="json", by_alias=True)
        if not old:
            if not command.confirmed or command.max_provider_calls != 1:
                raise RequirementCallConflict("model_authorization_required")
            if command.plan_digest != public["planDigest"]:
                raise RequirementCallConflict("extraction_plan_stale")
            if not public["available"]:
                raise RequirementCallConflict(public["blockerCode"])
        record, claimed = self.journal.reserve(job_id=job_id, action_id=command.action_id,
            command=content, snapshot=snapshot, acknowledged=command.acknowledged_prior_request_id)
        if not claimed:
            return record
        try:
            with self.extractor_factory(command.action_id, snapshot) as extractor:
                use_case = ExtractJobRequirementsUseCase(jobs=self.jobs,
                    workflow=ExtractJobRequirementsWorkflow(extractor, self.traces),
                    uow_factory=lambda: self.uow_factory(command.action_id),
                    query_repository=self.requirements, provider="openai")
                use_case.execute(job_id)
        except Exception as exc:
            # Stable reason classes only; exception text may contain model output or credentials.
            received = self.journal.get(job_id, command.action_id)
            if received and received["responseStatus"] == 402:
                code = "provider_payment_required"
            elif isinstance(exc, RequirementCallConflict):
                code = "execution_or_facts_changed"
            elif isinstance(exc, (JobDescriptionChangedDuringExtractionError, RequirementExtractionSupersededError)):
                code = "extraction_facts_changed"
            elif isinstance(exc, InvalidRequirementExtractorOutputError):
                code = "extraction_output_invalid"
            elif isinstance(exc, RequirementExtractorUnavailableError):
                code = "provider_unavailable"
            else:
                code = "extraction_not_saved"
            self.journal.fail(command.action_id, code)
        return self.journal.get(job_id, command.action_id)
