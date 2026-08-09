"""Deterministic recommendation policy for transient MatchReport v1."""
from __future__ import annotations

from app.application.eligibility import EligibilityDecision
from app.application.match_report.models import MatchRecommendation
from app.application.semantic_match import JobSemanticMatchResult, SemanticMatchVerdict
from app.domain.job_requirements import RequirementImportance


def recommend_match(result: JobSemanticMatchResult) -> MatchRecommendation:
    """Map trusted Eligibility + semantic assessments to a user recommendation.

    The policy is intentionally threshold-free in v1: no percentage score and no
    provider-owned recommendation. Deterministic Eligibility always has precedence.
    """

    if result.eligibility is EligibilityDecision.BLOCKED:
        return MatchRecommendation.BLOCKED
    if result.eligibility is EligibilityDecision.CONDITIONAL:
        return MatchRecommendation.STRETCH

    core = tuple(
        item
        for item in result.assessments
        if item.importance in {
            RequirementImportance.MUST_HAVE,
            RequirementImportance.PREFERRED,
        }
    )
    if not core:
        return (
            MatchRecommendation.GOOD
            if any(
                item.verdict is SemanticMatchVerdict.MATCHED
                for item in result.assessments
            )
            else MatchRecommendation.LOW
        )

    if all(item.verdict is SemanticMatchVerdict.MATCHED for item in core):
        return MatchRecommendation.STRONG
    if any(item.verdict is SemanticMatchVerdict.MATCHED for item in core):
        return MatchRecommendation.GOOD
    return MatchRecommendation.LOW
