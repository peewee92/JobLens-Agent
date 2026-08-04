"""Application models for preparing real Requirement manual-review batches."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RequirementAcceptanceCaseStatus(StrEnum):
    REUSED = "reused"
    EXTRACTED = "extracted"
    FAILED = "failed"
    DEFERRED = "deferred"


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceCaseResult:
    input_index: int
    job_id: str
    title: str
    company: str
    status: RequirementAcceptanceCaseStatus
    extraction_id: str | None
    trace_run_id: str | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class RequirementAcceptancePreparationResult:
    run_id: str
    dataset_fingerprint: str
    import_id: str
    source_version: str
    received: int
    created_jobs: int
    updated_jobs: int
    reused_extractions: int
    created_extractions: int
    failed_extractions: int
    deferred_extractions: int
    max_new_extractions: int | None
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    batch_id: str | None
    batch_reused: bool
    cases: tuple[RequirementAcceptanceCaseResult, ...]

    @property
    def ready_for_manual_review(self) -> bool:
        return (
            self.batch_id is not None
            and self.failed_extractions == 0
            and self.deferred_extractions == 0
        )
