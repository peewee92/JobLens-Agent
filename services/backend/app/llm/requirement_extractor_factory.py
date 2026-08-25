"""Runtime factory for the configured Job Requirement Extractor adapter."""
from __future__ import annotations

from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
from app.core.config import Settings
from app.llm.job_requirement_extractors import (
    DisabledJobRequirementExtractor,
    FallbackJobRequirementExtractor,
    FixtureJobRequirementExtractor,
    OpenAIJobRequirementExtractor,
)


def _build_adapter(
    settings: Settings,
    *,
    provider: str,
    model: str,
) -> AbstractJobRequirementExtractor:
    normalized_provider = provider.strip().casefold()
    if normalized_provider == "fixture":
        return FixtureJobRequirementExtractor()
    if normalized_provider == "openai":
        return OpenAIJobRequirementExtractor(
            api_key=settings.openai_api_key,
            model=model,
            base_url=settings.openai_base_url,
            api_style=settings.requirement_extractor_api_style,
            enable_thinking=settings.requirement_extractor_enable_thinking,
            max_completion_tokens=settings.requirement_extractor_max_completion_tokens,
            timeout_seconds=settings.requirement_extractor_timeout_seconds,
            circuit_failure_threshold=settings.requirement_extractor_circuit_failure_threshold,
            circuit_cooldown_seconds=settings.requirement_extractor_circuit_cooldown_seconds,
        )
    return DisabledJobRequirementExtractor()


def build_job_requirement_extractor(
    settings: Settings,
) -> AbstractJobRequirementExtractor:
    primary = _build_adapter(
        settings,
        provider=settings.requirement_extractor_provider,
        model=settings.requirement_extractor_model,
    )
    fallback_provider = settings.requirement_extractor_fallback_provider.strip().casefold()
    fallback_model = settings.requirement_extractor_fallback_model.strip()
    if fallback_provider != "openai" or not fallback_model:
        return primary
    fallback = _build_adapter(
        settings,
        provider=fallback_provider,
        model=fallback_model,
    )
    if isinstance(fallback, DisabledJobRequirementExtractor):
        return primary
    return FallbackJobRequirementExtractor(primary=primary, fallback=fallback)
