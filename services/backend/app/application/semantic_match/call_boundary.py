"""Shared need-for-model rule, not authorization and not an actual call counter."""
from collections.abc import Sequence
from app.application.eligibility import RequirementFitStatus
from app.application.eligibility.models import RequirementEligibilityResult
from app.application.evidence_retrieval.models import CandidateEvidence
from app.application.semantic_match.models import SemanticRequirementInput, SemanticCandidateInput


def needs_semantic_model(status: RequirementFitStatus, candidates: Sequence[CandidateEvidence]) -> bool:
    return status is not RequirementFitStatus.MATCHED and bool(candidates)


def semantic_requirement_input(
    item: RequirementEligibilityResult, candidates: Sequence[CandidateEvidence],
) -> SemanticRequirementInput:
    """The same bounded input is previewed, size-checked and sent by the workflow."""
    return SemanticRequirementInput(
        requirement_id=item.requirement_id, requirement_index=item.requirement_index,
        type=item.type, importance=item.importance, original_text=item.original_text,
        normalized_capability=item.normalized_capability,
        candidates=tuple(SemanticCandidateInput(
            evidence_id=c.evidence_id, evidence_type=c.evidence_type, summary=c.summary,
            relevance_tier=c.relevance_tier, retrieval_basis=c.retrieval_basis) for c in candidates))


def semantic_input_payload(requirements: tuple[SemanticRequirementInput, ...]) -> dict[str, object]:
    return {
        "requirements": [
            {
                "requirementId": item.requirement_id,
                "type": item.type.value,
                "importance": item.importance.value,
                "originalText": item.original_text,
                "normalizedCapability": item.normalized_capability,
                "candidates": [
                    {
                        "evidenceId": candidate.evidence_id,
                        "evidenceType": candidate.evidence_type.value,
                        "summary": candidate.summary,
                        "relevanceTier": candidate.relevance_tier.value,
                        "retrievalBasis": candidate.retrieval_basis.value,
                    }
                    for candidate in item.candidates
                ],
            }
            for item in requirements
        ]
    }
