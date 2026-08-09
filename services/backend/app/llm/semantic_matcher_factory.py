"""Runtime factory for the configured Semantic Match adapter."""
from __future__ import annotations

from app.application.ports.semantic_matcher import AbstractSemanticMatcher
from app.core.config import Settings
from app.llm.semantic_matchers import (
    DisabledSemanticMatcher,
    FixtureSemanticMatcher,
    OpenAISemanticMatcher,
)


def build_semantic_matcher(settings: Settings) -> AbstractSemanticMatcher:
    provider = settings.semantic_match_provider.strip().casefold()
    if provider == "fixture":
        return FixtureSemanticMatcher()
    if provider == "openai":
        return OpenAISemanticMatcher(
            api_key=settings.openai_api_key,
            model=settings.semantic_match_model,
            base_url=settings.openai_base_url,
            api_style=settings.semantic_match_api_style,
            enable_thinking=settings.semantic_match_enable_thinking,
            max_completion_tokens=settings.semantic_match_max_completion_tokens,
            timeout_seconds=settings.semantic_match_timeout_seconds,
        )
    return DisabledSemanticMatcher()
