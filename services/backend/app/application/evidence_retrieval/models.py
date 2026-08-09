"""Read-only Phase 4 Evidence Retrieval models."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.career_context import EvidenceType
from app.domain.job_requirements import RequirementImportance, RequirementType


class EvidenceRelevanceTier(StrEnum):
    DIRECT = "direct"
    RELATED = "related"


class EvidenceRetrievalBasis(StrEnum):
    EXACT_SKILL_LINK = "exact_skill_link"
    EXPLICIT_TEXT_OVERLAP = "explicit_text_overlap"
    RELATED_CAPABILITY_HINT = "related_capability_hint"


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    evidence_id: str
    evidence_key: str
    evidence_type: EvidenceType
    summary: str
    source: str
    relevance_tier: EvidenceRelevanceTier
    retrieval_basis: EvidenceRetrievalBasis
    matched_terms: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class RequirementEvidenceCandidates:
    requirement_id: str
    requirement_index: int
    type: RequirementType
    importance: RequirementImportance
    original_text: str
    normalized_capability: str | None
    candidates: tuple[CandidateEvidence, ...]


@dataclass(frozen=True, slots=True)
class JobEvidenceRetrievalResult:
    job_id: str
    profile_id: str
    profile_version: int
    extraction_id: str
    requirements: tuple[RequirementEvidenceCandidates, ...]
    candidate_count: int
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0
