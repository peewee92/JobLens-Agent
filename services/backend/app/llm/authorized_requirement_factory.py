"""A single bounded adapter, without fallback or automatic HTTP retries."""
from contextlib import contextmanager
from dataclasses import replace
from app.application.ports.job_requirement_extractor import AbstractJobRequirementExtractor
from app.application.job_requirements import RequirementExtractorFailedError, RequirementExtractorUnavailableError
import httpx
from app.llm.job_requirement_extractors import OpenAIJobRequirementExtractor
from app.llm.journaled_requirement_transport import JournaledTransport


class _JournaledExtractor(AbstractJobRequirementExtractor):
    """Trace counts come from the durable dispatch boundary, not a client.post counter."""
    def __init__(self, adapter, journal, job_id, action_id):
        self.adapter, self.journal = adapter, journal
        self.job_id, self.action_id = job_id, action_id

    @property
    def model_name(self):
        return self.adapter.model_name

    @property
    def max_provider_calls_per_execution(self):
        return 1

    def extract(self, description):
        try:
            result = self.adapter.extract(description)
        except Exception as exc:
            attempts = self.journal.get(self.job_id, self.action_id)["attempts"]
            if isinstance(exc, (RequirementExtractorFailedError, RequirementExtractorUnavailableError)):
                exc.provider_calls = attempts
                raise
            raise RequirementExtractorFailedError(
                "Authorized extraction interrupted before usable output", provider_calls=attempts,
            ) from exc
        return replace(result, provider_calls=self.journal.get(self.job_id, self.action_id)["attempts"])


def authorized_extractor_factory(settings, journal, transport_factory=None):
    make_transport = transport_factory or (lambda: httpx.HTTPTransport(retries=0))

    @contextmanager
    def create(action_id, snapshot):
        transport = JournaledTransport(journal, action_id, make_transport())
        with httpx.Client(transport=transport, timeout=snapshot["timeoutSeconds"], follow_redirects=False) as client:
            adapter = OpenAIJobRequirementExtractor(api_key=settings.openai_api_key,
                model=snapshot["model"], base_url=settings.openai_base_url,
                api_style=settings.requirement_extractor_api_style,
                enable_thinking=settings.requirement_extractor_enable_thinking,
                max_completion_tokens=snapshot["maxOutputTokens"],
                timeout_seconds=snapshot["timeoutSeconds"], retry_max_attempts=1, client=client)
            yield _JournaledExtractor(adapter, journal, snapshot["jobId"], action_id)
    return create
