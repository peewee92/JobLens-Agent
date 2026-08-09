"""Phase 4 Semantic Match models that preserve deterministic Eligibility."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.eligibility.models import EligibilityDecision, RequirementFitStatus
from app.application.evidence_retrieval.models import (
    EvidenceRelevanceTier,
    EvidenceRetrievalBasis,
)
from app.domain.career_context import EvidenceType
from app.domain.job_requirements import RequirementImportance, RequirementType


class SemanticMatchVerdict(StrEnum):
    MATCHED = "matched"
    PARTIAL = "partial"
    NOT_MATCHED = "not_matched"


class SemanticAssessmentSource(StrEnum):
    DETERMINISTIC = "deterministic"
    PROVIDER = "provider"


@dataclass(frozen=True, slots=True)
class SemanticCandidateInput:
    evidence_id: str
    evidence_type: EvidenceType
    summary: str
    relevance_tier: EvidenceRelevanceTier
    retrieval_basis: EvidenceRetrievalBasis


@dataclass(frozen=True, slots=True)
class SemanticRequirementInput:
    requirement_id: str
    requirement_index: int
    type: RequirementType
    importance: RequirementImportance
    original_text: str
    normalized_capability: str | None
    candidates: tuple[SemanticCandidateInput, ...]


@dataclass(frozen=True, slots=True)
class SemanticMatchAssessmentOutput:
    requirement_id: str
    verdict: SemanticMatchVerdict
    evidence_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class SemanticMatchOutput:
    assessments: tuple[SemanticMatchAssessmentOutput, ...]


@dataclass(frozen=True, slots=True)
class SemanticMatcherResult:
    output: SemanticMatchOutput
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class SemanticRequirementAssessment:
    requirement_id: str
    requirement_index: int
    type: RequirementType
    importance: RequirementImportance
    original_text: str
    normalized_capability: str | None
    eligibility_status: RequirementFitStatus
    verdict: SemanticMatchVerdict
    evidence_ids: tuple[str, ...]
    profile_fact_refs: tuple[str, ...]
    reason: str
    source: SemanticAssessmentSource


@dataclass(frozen=True, slots=True)
class JobSemanticMatchResult:
    job_id: str
    profile_id: str
    profile_version: int
    extraction_id: str
    eligibility: EligibilityDecision
    assessments: tuple[SemanticRequirementAssessment, ...]
    matched_count: int
    partial_count: int
    not_matched_count: int
    matcher_version: str
    prompt_version: str
    model: str | None
    trace_run_id: str | None
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0
