"""LLM and deterministic extractor adapters."""

from app.llm.factory import build_profile_extractor
from app.llm.job_requirement_extractors import (
    DisabledJobRequirementExtractor,
    FallbackJobRequirementExtractor,
    FixtureJobRequirementExtractor,
    OpenAIJobRequirementExtractor,
)
from app.llm.requirement_extractor_factory import build_job_requirement_extractor
from app.llm.semantic_matcher_factory import build_semantic_matcher
from app.llm.semantic_matchers import (
    DisabledSemanticMatcher,
    FixtureSemanticMatcher,
    OpenAISemanticMatcher,
)
from app.llm.profile_extractors import (
    DisabledProfileExtractor,
    FixtureProfileExtractor,
    OpenAIProfileExtractor,
)

__all__ = [
    "DisabledJobRequirementExtractor",
    "DisabledProfileExtractor",
    "DisabledSemanticMatcher",
    "FallbackJobRequirementExtractor",
    "FixtureJobRequirementExtractor",
    "FixtureProfileExtractor",
    "FixtureSemanticMatcher",
    "OpenAIJobRequirementExtractor",
    "OpenAIProfileExtractor",
    "OpenAISemanticMatcher",
    "build_job_requirement_extractor",
    "build_profile_extractor",
    "build_semantic_matcher",
]
