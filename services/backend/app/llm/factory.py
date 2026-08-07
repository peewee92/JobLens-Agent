"""Runtime factory for the configured Profile Extractor adapter."""
from __future__ import annotations

from app.application.ports.profile_extractor import AbstractProfileExtractor
from app.core.config import Settings
from app.llm.profile_extractors import (
    DisabledProfileExtractor,
    FixtureProfileExtractor,
    OpenAIProfileExtractor,
)


def build_profile_extractor(settings: Settings) -> AbstractProfileExtractor:
    provider = settings.profile_extractor_provider.strip().casefold()
    if provider == "fixture":
        return FixtureProfileExtractor()
    if provider == "openai":
        return OpenAIProfileExtractor(
            api_key=settings.openai_api_key,
            model=settings.profile_extractor_model,
            base_url=settings.openai_base_url,
            api_style=settings.profile_extractor_api_style,
            enable_thinking=settings.profile_extractor_enable_thinking,
            max_completion_tokens=settings.profile_extractor_max_completion_tokens,
            timeout_seconds=settings.profile_extractor_timeout_seconds,
        )
    return DisabledProfileExtractor()
