"""HTTP response models for Job Requirement Extraction Runs."""
from __future__ import annotations

from datetime import datetime

from app.api.v1.schemas.common import CamelCaseModel
from app.application.job_requirements import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
)
from app.domain.job_requirements import RequirementImportance, RequirementType


class JobRequirementResponse(CamelCaseModel):
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

    @classmethod
    def from_detail(cls, detail: JobRequirementDetail) -> "JobRequirementResponse":
        return cls(
            id=detail.id,
            job_id=detail.job_id,
            extraction_id=detail.extraction_id,
            requirement_index=detail.requirement_index,
            type=detail.type,
            original_text=detail.original_text,
            normalized_capability=detail.normalized_capability,
            importance=detail.importance,
            evidence_span=detail.evidence_span,
            confidence=detail.confidence,
            extractor_version=detail.extractor_version,
        )


class JobRequirementExtractionResponse(CamelCaseModel):
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
    requirements: list[JobRequirementResponse]

    @classmethod
    def from_detail(
        cls,
        detail: JobRequirementExtractionDetail,
    ) -> "JobRequirementExtractionResponse":
        return cls(
            extraction_id=detail.extraction_id,
            job_id=detail.job_id,
            input_hash=detail.input_hash,
            extractor_version=detail.extractor_version,
            provider=detail.provider,
            model=detail.model,
            prompt_version=detail.prompt_version,
            trace_run_id=detail.trace_run_id,
            requirement_count=detail.requirement_count,
            created_at=detail.created_at,
            requirements=[
                JobRequirementResponse.from_detail(item)
                for item in detail.requirements
            ],
        )
