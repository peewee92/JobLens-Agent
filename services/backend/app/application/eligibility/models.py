"""Read-only Phase 4 Eligibility models."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.job_requirements import RequirementImportance, RequirementType


class RequirementFitStatus(StrEnum):
    MATCHED = "matched"
    CONDITIONAL = "conditional"
    MISSING = "missing"


class EligibilityDecision(StrEnum):
    ELIGIBLE = "eligible"
    CONDITIONAL = "conditional"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class RequirementEligibilityResult:
    requirement_id: str
    requirement_index: int
    type: RequirementType
    importance: RequirementImportance
    original_text: str
    normalized_capability: str | None
    status: RequirementFitStatus
    evidence_ids: tuple[str, ...]
    profile_fact_refs: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class JobEligibilityResult:
    job_id: str
    profile_id: str
    profile_version: int
    extraction_id: str
    eligibility: EligibilityDecision
    requirements: tuple[RequirementEligibilityResult, ...]
    matched_count: int
    conditional_count: int
    missing_count: int
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0
