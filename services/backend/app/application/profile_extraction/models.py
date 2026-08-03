"""Application models for resume-to-Profile proposal extraction."""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.career_context import EvidenceType, SkillLevel


@dataclass(frozen=True, slots=True)
class ProposedEvidence:
    key: str
    type: EvidenceType
    summary: str
    source: str
    evidence_span: str


@dataclass(frozen=True, slots=True)
class ProposedSkill:
    name: str
    level: SkillLevel
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfileExtractionOutput:
    headline: str
    years_of_experience: float | None
    evidence: tuple[ProposedEvidence, ...]
    skills: tuple[ProposedSkill, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfileExtractorResult:
    output: ProfileExtractionOutput
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ProfileExtractionProposal:
    run_id: str
    extractor_version: str
    model: str
    prompt_version: str
    headline: str
    years_of_experience: float | None
    evidence: tuple[ProposedEvidence, ...]
    skills: tuple[ProposedSkill, ...]
    warnings: tuple[str, ...]
