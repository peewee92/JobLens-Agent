"""Application models for Job Requirement extraction and persistence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.job_requirements import RequirementImportance, RequirementType


@dataclass(frozen=True, slots=True)
class ProposedJobRequirement:
    type: RequirementType
    original_text: str
    normalized_capability: str | None
    importance: RequirementImportance
    evidence_span: str
    confidence: float


@dataclass(frozen=True, slots=True)
class JobRequirementExtractionOutput:
    requirements: tuple[ProposedJobRequirement, ...]


@dataclass(frozen=True, slots=True)
class JobRequirementExtractorResult:
    output: JobRequirementExtractionOutput
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class JobRequirementExtractionProposal:
    trace_run_id: str
    extractor_version: str
    model: str
    prompt_version: str
    requirements: tuple[ProposedJobRequirement, ...]


@dataclass(frozen=True, slots=True)
class JobRequirementWrite:
    requirement_id: str
    job_id: str
    requirement_index: int
    type: RequirementType
    original_text: str
    normalized_capability: str | None
    importance: RequirementImportance
    evidence_span: str
    confidence: float
    extractor_version: str


@dataclass(frozen=True, slots=True)
class JobRequirementExtractionWrite:
    extraction_id: str
    job_id: str
    input_hash: str
    description_characters: int
    extractor_version: str
    provider: str
    model: str
    prompt_version: str
    trace_run_id: str
    requirements: tuple[JobRequirementWrite, ...]


@dataclass(frozen=True, slots=True)
class JobRequirementDetail:
    id: str
    job_id: str
    extraction_id: str
    requirement_index: int
    type: RequirementType
    original_text: str
    normalized_capability: str | None
    importance: RequirementImportance
    evidence_span: str
    confidence: float
    extractor_version: str


@dataclass(frozen=True, slots=True)
class JobRequirementExtractionDetail:
    extraction_id: str
    job_id: str
    input_hash: str
    extractor_version: str
    provider: str
    model: str
    prompt_version: str
    trace_run_id: str
    requirement_count: int
    created_at: datetime
    requirements: tuple[JobRequirementDetail, ...]
