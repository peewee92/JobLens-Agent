"""HTTP schemas for Requirement manual quality review batches."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from app.api.v1.schemas.common import CamelCaseModel
from app.api.v1.schemas.job_requirements import JobRequirementResponse
from app.application.requirement_reviews import (
    RequirementReviewBatchCaseDetail,
    RequirementReviewBatchDetail,
    RequirementReviewBatchPage,
    RequirementReviewBatchSummary,
    RequirementReviewCandidate,
    RequirementReviewCandidatePage,
    RequirementReviewCaseReviewDetail,
    RequirementReviewDecision,
    RequirementReviewIssueCode,
)


class RequirementReviewCandidateResponse(CamelCaseModel):
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

    @classmethod
    def from_candidate(
        cls,
        candidate: RequirementReviewCandidate,
    ) -> "RequirementReviewCandidateResponse":
        return cls(**asdict(candidate))


class RequirementReviewCandidatePageResponse(CamelCaseModel):
    total: int
    limit: int
    offset: int
    items: list[RequirementReviewCandidateResponse]

    @classmethod
    def from_page(
        cls,
        page: RequirementReviewCandidatePage,
    ) -> "RequirementReviewCandidatePageResponse":
        return cls(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            items=[RequirementReviewCandidateResponse.from_candidate(item) for item in page.items],
        )


class CreateRequirementReviewBatchRequest(CamelCaseModel):
    title: str
    reviewer: str
    extraction_ids: list[str]


class RequirementReviewCaseReviewRequest(CamelCaseModel):
    decision: RequirementReviewDecision
    issue_codes: list[RequirementReviewIssueCode]
    notes: str


class RequirementReviewCaseReviewResponse(CamelCaseModel):
    id: str
    batch_case_id: str
    decision: RequirementReviewDecision
    issue_codes: list[RequirementReviewIssueCode]
    notes: str
    reviewed_at: datetime

    @classmethod
    def from_detail(
        cls,
        detail: RequirementReviewCaseReviewDetail,
    ) -> "RequirementReviewCaseReviewResponse":
        return cls(
            id=detail.id,
            batch_case_id=detail.batch_case_id,
            decision=detail.decision,
            issue_codes=list(detail.issue_codes),
            notes=detail.notes,
            reviewed_at=detail.reviewed_at,
        )


class RequirementReviewBatchSummaryResponse(CamelCaseModel):
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
    created_at: datetime

    @classmethod
    def from_summary(
        cls,
        summary: RequirementReviewBatchSummary,
    ) -> "RequirementReviewBatchSummaryResponse":
        return cls(**asdict(summary))


class RequirementReviewBatchCaseResponse(CamelCaseModel):
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
    requirements: list[JobRequirementResponse]
    review: RequirementReviewCaseReviewResponse | None

    @classmethod
    def from_detail(
        cls,
        detail: RequirementReviewBatchCaseDetail,
    ) -> "RequirementReviewBatchCaseResponse":
        return cls(
            id=detail.id,
            case_index=detail.case_index,
            job_id=detail.job_id,
            extraction_id=detail.extraction_id,
            title=detail.title,
            company=detail.company,
            description=detail.description,
            provider=detail.provider,
            model=detail.model,
            extractor_version=detail.extractor_version,
            prompt_version=detail.prompt_version,
            trace_run_id=detail.trace_run_id,
            created_at=detail.created_at,
            is_current=detail.is_current,
            requirements=[JobRequirementResponse.from_detail(item) for item in detail.requirements],
            review=(
                RequirementReviewCaseReviewResponse.from_detail(detail.review)
                if detail.review is not None
                else None
            ),
        )


class RequirementReviewBatchDetailResponse(CamelCaseModel):
    summary: RequirementReviewBatchSummaryResponse
    issue_code_counts: dict[str, int]
    cases: list[RequirementReviewBatchCaseResponse]

    @classmethod
    def from_detail(
        cls,
        detail: RequirementReviewBatchDetail,
    ) -> "RequirementReviewBatchDetailResponse":
        return cls(
            summary=RequirementReviewBatchSummaryResponse.from_summary(detail.summary),
            issue_code_counts=dict(detail.issue_code_counts),
            cases=[RequirementReviewBatchCaseResponse.from_detail(item) for item in detail.cases],
        )


class RequirementReviewBatchPageResponse(CamelCaseModel):
    total: int
    limit: int
    offset: int
    items: list[RequirementReviewBatchSummaryResponse]

    @classmethod
    def from_page(
        cls,
        page: RequirementReviewBatchPage,
    ) -> "RequirementReviewBatchPageResponse":
        return cls(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            items=[RequirementReviewBatchSummaryResponse.from_summary(item) for item in page.items],
        )
