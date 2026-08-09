"""Semantic Match application surface."""

from app.application.semantic_match.errors import (
    InvalidSemanticMatcherOutputError,
    SemanticMatcherFailedError,
    SemanticMatcherUnavailableError,
    SemanticMatchInputsNotReadyError,
)
from app.application.semantic_match.models import (
    JobSemanticMatchResult,
    SemanticAssessmentSource,
    SemanticCandidateInput,
    SemanticMatchAssessmentOutput,
    SemanticMatchOutput,
    SemanticMatcherResult,
    SemanticMatchVerdict,
    SemanticRequirementAssessment,
    SemanticRequirementInput,
)

__all__ = [
    "InvalidSemanticMatcherOutputError",
    "JobSemanticMatchResult",
    "SemanticAssessmentSource",
    "SemanticCandidateInput",
    "SemanticMatchAssessmentOutput",
    "SemanticMatchInputsNotReadyError",
    "SemanticMatchOutput",
    "SemanticMatcherFailedError",
    "SemanticMatcherResult",
    "SemanticMatcherUnavailableError",
    "SemanticMatchVerdict",
    "SemanticRequirementAssessment",
    "SemanticRequirementInput",
]
