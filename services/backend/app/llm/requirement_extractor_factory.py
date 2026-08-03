"""Runtime factory for the configured Job Requirement Extractor adapter."""
from __future__ import annotations

from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
from app.core.config import Settings
from app.llm.job_requirement_extractors import (
    DisabledJobRequirementExtractor,
    FixtureJobRequirementExtractor,
    OpenAIJobRequirementExtractor,
)


def build_job_requirement_extractor(
    settings: Settings,
) -> AbstractJobRequirementExtractor:
    provider = settings.requirement_extractor_provider.strip().casefold()
    if provider == "fixture":
        return FixtureJobRequirementExtractor()
    if provider == "openai":
        return OpenAIJobRequirementExtractor(
            api_key=settings.openai_api_key,
            model=settings.requirement_extractor_model,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.requirement_extractor_timeout_seconds,
        )
    return DisabledJobRequirementExtractor()
