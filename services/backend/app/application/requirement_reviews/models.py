"""Application models for version-frozen Requirement manual review batches."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.application.job_requirements import JobRequirementDetail


class RequirementReviewDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RequirementReviewBatchFinalDecision(StrEnum):
    ACCEPT_FOR_MATCH = "accept_for_match"
    REJECT_FOR_MATCH = "reject_for_match"


class RequirementReviewIssueCode(StrEnum):
    MISSING_REQUIREMENT = "missing_requirement"
    UNSUPPORTED_REQUIREMENT = "unsupported_requirement"
    WRONG_IMPORTANCE = "wrong_importance"
    WRONG_TYPE = "wrong_type"
    WRONG_NORMALIZATION = "wrong_normalization"
    EVIDENCE_MISMATCH = "evidence_mismatch"
    DUPLICATE_REQUIREMENT = "duplicate_requirement"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class RequirementReviewCandidate:
    extraction_id: str
    job_id: str
    title: str
    company: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    trace_run_id: str
    requirement_count: int
    created_at: datetime
    semantic_policy_version: str | None = None


@dataclass(frozen=True, slots=True)
class RequirementReviewCandidatePage:
    total: int
    limit: int
    offset: int
    items: tuple[RequirementReviewCandidate, ...]


@dataclass(frozen=True, slots=True)
class RequirementReviewExtractionSnapshot:
    extraction_id: str
    job_id: str
    title: str
    company: str
    description: str | None
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    trace_run_id: str
    requirement_count: int
    created_at: datetime
    is_current: bool
    semantic_policy_version: str | None = None


@dataclass(frozen=True, slots=True)
class RequirementReviewBatchCaseWrite:
    case_id: str
    case_index: int
    job_id: str
    extraction_id: str


@dataclass(frozen=True, slots=True)
class RequirementReviewBatchWrite:
    batch_id: str
    title: str
    reviewer: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    cases: tuple[RequirementReviewBatchCaseWrite, ...]


@dataclass(frozen=True, slots=True)
class RequirementReviewCaseReviewWrite:
    review_id: str
    batch_case_id: str
    decision: RequirementReviewDecision
    issue_codes: tuple[RequirementReviewIssueCode, ...]
    notes: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class RequirementReviewCaseReviewDetail:
    id: str
    batch_case_id: str
    decision: RequirementReviewDecision
    issue_codes: tuple[RequirementReviewIssueCode, ...]
    notes: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class RequirementReviewBatchFinalDecisionWrite:
    decision_id: str
    batch_id: str
    decision: RequirementReviewBatchFinalDecision
    reviewer: str
    notes: str
    sample_size: int
    reviewed_count: int
    accepted_count: int
    rejected_count: int
    stale_case_count: int
    issue_code_counts: dict[str, int]
    evidence_fingerprint: str
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class RequirementReviewBatchFinalDecisionDetail:
    id: str
    batch_id: str
    decision: RequirementReviewBatchFinalDecision
    reviewer: str
    notes: str
    sample_size: int
    reviewed_count: int
    accepted_count: int
    rejected_count: int
    stale_case_count: int
    issue_code_counts: dict[str, int]
    evidence_fingerprint: str
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class RequirementReviewBatchCaseLookup:
    batch_id: str
    batch_case_id: str
    review: RequirementReviewCaseReviewDetail | None


@dataclass(frozen=True, slots=True)
class RequirementReviewBatchCaseDetail:
    id: str
    case_index: int
    job_id: str
    extraction_id: str
    title: str
    company: str
    description: str | None
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    trace_run_id: str
    created_at: datetime
    is_current: bool
    requirements: tuple[JobRequirementDetail, ...]
    review: RequirementReviewCaseReviewDetail | None
    semantic_policy_version: str | None = None


@dataclass(frozen=True, slots=True)
class RequirementReviewBatchSummary:
    id: str
    title: str
    reviewer: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    sample_size: int
    reviewed_count: int
    accepted_count: int
    rejected_count: int
    stale_case_count: int
    completed: bool
    formal_evidence_eligible: bool
    final_decision: RequirementReviewBatchFinalDecision | None
    match_release_eligible: bool
    created_at: datetime
    semantic_policy_version: str | None = None


@dataclass(frozen=True, slots=True)
class RequirementReviewBatchDetail:
    summary: RequirementReviewBatchSummary
    issue_code_counts: dict[str, int]
    cases: tuple[RequirementReviewBatchCaseDetail, ...]
    final_decision: RequirementReviewBatchFinalDecisionDetail | None


@dataclass(frozen=True, slots=True)
class AcceptedRequirementReviewBaseline:
    decision: RequirementReviewBatchFinalDecisionDetail
    batch: RequirementReviewBatchSummary
    issue_code_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class RequirementReviewBatchPage:
    total: int
    limit: int
    offset: int
    items: tuple[RequirementReviewBatchSummary, ...]
