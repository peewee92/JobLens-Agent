"""Persistent execution records for controlled Requirement acceptance preparation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RequirementAcceptanceRunCaseStatus(StrEnum):
    PENDING = "pending"
    REUSED = "reused"
    EXTRACTED = "extracted"
    FAILED = "failed"
    DEFERRED = "deferred"


class RequirementAcceptanceRunStatus(StrEnum):
    PENDING = "pending"
    PARTIAL = "partial"
    AWAITING_CANARY_REVIEW = "awaiting_canary_review"
    STOPPED = "stopped"
    READY = "ready"


class RequirementAcceptanceCanaryDecision(StrEnum):
    CONTINUE = "continue"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class RequirementAcceptancePreflight:
    dataset_fingerprint: str
    source_version: str
    generated_at: str | None
    selected_count: int
    total_description_characters: int
    minimum_description_characters: int
    maximum_description_characters: int
    average_description_characters: float


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceRunCaseWrite:
    case_id: str
    case_index: int
    source_url: str
    title: str
    company: str
    description_hash: str
    description_snapshot: str
    job_id: str


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceRunWrite:
    run_id: str
    dataset_fingerprint: str
    source_version: str
    dataset_generated_at: str | None
    title: str
    reviewer: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    first_import_id: str
    last_import_id: str
    cases: tuple[RequirementAcceptanceRunCaseWrite, ...]


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceRunCaseUpdate:
    run_id: str
    case_index: int
    status: RequirementAcceptanceRunCaseStatus
    job_id: str
    attempt_increment: int
    extraction_id: str | None
    trace_run_id: str | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceRunCaseDetail:
    id: str
    case_index: int
    source_url: str
    title: str
    company: str
    description_hash: str
    description_snapshot: str | None
    current_description_hash: str
    description_is_current: bool
    job_id: str
    status: RequirementAcceptanceRunCaseStatus
    attempt_count: int
    extraction_id: str | None
    trace_run_id: str | None
    trace_capability: str | None
    trace_model: str | None
    trace_prompt_version: str | None
    trace_latency_ms: int | None
    trace_input_tokens: int | None
    trace_output_tokens: int | None
    trace_error: str | None
    trace_created_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def was_attempted(self) -> bool:
        return self.attempt_count > 0


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceCanaryReviewWrite:
    review_id: str
    run_id: str
    reviewer: str
    decision: RequirementAcceptanceCanaryDecision
    notes: str
    reviewed_case_ids: tuple[str, ...]
    reviewed_extraction_ids: tuple[str, ...]
    reviewed_trace_run_ids: tuple[str, ...]
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceCanaryReviewDetail:
    id: str
    run_id: str
    reviewer: str
    decision: RequirementAcceptanceCanaryDecision
    notes: str
    reviewed_case_ids: tuple[str, ...]
    reviewed_extraction_ids: tuple[str, ...]
    reviewed_trace_run_ids: tuple[str, ...]
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceRunDetail:
    id: str
    dataset_fingerprint: str
    source_version: str
    dataset_generated_at: str | None
    title: str
    reviewer: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    first_import_id: str
    last_import_id: str
    batch_id: str | None
    status: RequirementAcceptanceRunStatus
    canary_review_required: bool
    canary_review: RequirementAcceptanceCanaryReviewDetail | None
    pending_count: int
    reused_count: int
    extracted_count: int
    failed_count: int
    deferred_count: int
    attempted_calls: int
    created_at: datetime
    updated_at: datetime
    cases: tuple[RequirementAcceptanceRunCaseDetail, ...]

    @property
    def completed_case_count(self) -> int:
        return self.reused_count + self.extracted_count

    @property
    def canary_stop_allowed(self) -> bool:
        if self.provider.casefold() != "openai":
            return False
        if self.batch_id is not None or self.canary_review is not None:
            return False
        if not 1 <= self.attempted_calls <= 3:
            return False
        attempted_cases = tuple(case for case in self.cases if case.was_attempted)
        return bool(attempted_cases) and all(
            case.trace_run_id is not None for case in attempted_cases
        )

    @property
    def canary_continue_allowed(self) -> bool:
        if not self.canary_stop_allowed:
            return False
        return any(
            case.was_attempted and case.extraction_id is not None
            for case in self.cases
        )

    @property
    def canary_review_block_reason(self) -> str | None:
        if self.provider.casefold() != "openai":
            return "Only live OpenAI runs require a formal Canary decision."
        if self.batch_id is not None:
            return "The Run already has a frozen Review Batch."
        if self.canary_review is not None:
            return "The Run already has an immutable Canary decision."
        if self.attempted_calls == 0:
            return "Run at least one live Canary Extraction before reviewing."
        if self.attempted_calls > 3:
            return "Canary review is invalid after more than three cumulative live attempts."
        attempted_cases = tuple(case for case in self.cases if case.was_attempted)
        if any(case.trace_run_id is None for case in attempted_cases):
            return "Every attempted Canary case must have a Trace before review."
        if not any(case.extraction_id is not None for case in attempted_cases):
            return "Continue is unavailable because no Canary Extraction succeeded; Stop remains available."
        return None


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceRunSummary:
    id: str
    title: str
    reviewer: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    status: RequirementAcceptanceRunStatus
    attempted_calls: int
    completed_case_count: int
    failed_count: int
    deferred_count: int
    canary_review_required: bool
    canary_decision: RequirementAcceptanceCanaryDecision | None
    batch_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceRunPage:
    total: int
    limit: int
    offset: int
    items: tuple[RequirementAcceptanceRunSummary, ...]
