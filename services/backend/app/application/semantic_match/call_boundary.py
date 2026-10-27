"""Shared need-for-model rule, not authorization and not an actual call counter."""
from collections.abc import Sequence
from app.application.eligibility import RequirementFitStatus
from app.application.evidence_retrieval.models import CandidateEvidence


def needs_semantic_model(status: RequirementFitStatus, candidates: Sequence[CandidateEvidence]) -> bool:
    return status is not RequirementFitStatus.MATCHED and bool(candidates)
