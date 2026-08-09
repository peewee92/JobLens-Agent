"""Transient Phase 4 MatchReport models."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.eligibility import EligibilityDecision, RequirementFitStatus
from app.application.semantic_match import SemanticMatchVerdict
from app.domain.job_requirements import RequirementImportance, RequirementType


class MatchRecommendation(StrEnum):
    STRONG = "strong"
    GOOD = "good"
    STRETCH = "stretch"
    LOW = "low"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class MatchReportRequirementResult:
    requirement_id: str
    requirement_index: int
    type: RequirementType
    importance: RequirementImportance
    original_text: str
    normalized_capability: str | None
    eligibility_status: RequirementFitStatus
    semantic_verdict: SemanticMatchVerdict
    evidence_ids: tuple[str, ...]
    profile_fact_refs: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class MatchReportInsight:
    requirement_id: str
    requirement_text: str
    reason: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchEvidenceLink:
    requirement_id: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchReport:
    job_id: str
    profile_id: str
    profile_version: int
    extraction_id: str
    eligibility: EligibilityDecision
    recommendation: MatchRecommendation
    summary: str
    strengths: tuple[MatchReportInsight, ...]
    risks: tuple[MatchReportInsight, ...]
    requirement_results: tuple[MatchReportRequirementResult, ...]
    matched_requirement_ids: tuple[str, ...]
    partial_requirement_ids: tuple[str, ...]
    missing_requirement_ids: tuple[str, ...]
    evidence_links: tuple[MatchEvidenceLink, ...]
    matcher_version: str
    prompt_version: str
    model: str | None
    trace_run_id: str | None
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0
