"""HTTP response models for persisted Requirement Eval runs."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from app.api.v1.schemas.common import CamelCaseModel
from app.evals.mvp_quality import MvpQualityStatus
from app.application.requirement_evals import (
    AcceptedRequirementEvalBaseline,
    RequirementEvalCaseDetail,
    RequirementEvalMetricComparison,
    RequirementEvalReviewDecision,
    RequirementEvalReviewDetail,
    RequirementEvalRunDetail,
    RequirementEvalRunPage,
    RequirementEvalRunSummary,
)


class MvpQualityStatusResponse(CamelCaseModel):
    gate_passed: bool
    replay_passed: bool
    replay_passed_cases: int
    replay_total_cases: int
    match_demo_passed: bool
    match_demo_persisted_reports: int
    match_demo_top_jobs: int
    match_demo_evidence_complete: bool
    provider_smoke_state: str
    provider_smoke_ready: bool | None
    provider_smoke_blocking: bool
    provider_smoke_blocker: str | None
    provider_smoke_checked_at: str | None
    provider_smoke_plain_status_code: int | None
    provider_smoke_structured_status_code: int | None
    provider_calls: int

    @classmethod
    def from_status(cls, status: MvpQualityStatus) -> "MvpQualityStatusResponse":
        return cls(**asdict(status))


class RequirementEvalRunSummaryResponse(CamelCaseModel):
    id: str
    dataset_version: str
    mode: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    gate_version: str
    baseline_run_id: str | None
    total_cases: int
    passed_cases: int
    case_pass_rate: float
    workflow_success_rate: float
    capability_recall: float
    importance_accuracy: float
    forbidden_capability_rate: float
    gate_passed: bool
    release_eligible: bool
    created_at: datetime

    @classmethod
    def from_summary(
        cls, summary: RequirementEvalRunSummary
    ) -> "RequirementEvalRunSummaryResponse":
        return cls(**asdict(summary))


class RequirementEvalCaseResponse(CamelCaseModel):
    case_id: str
    trace_run_id: str | None
    workflow_succeeded: bool
    passed: bool
    missing_requirements: list[str]
    wrong_importance: list[str]
    observed_forbidden_capabilities: list[str]
    actual_requirements: list[str]
    error: str | None

    @classmethod
    def from_detail(
        cls, detail: RequirementEvalCaseDetail
    ) -> "RequirementEvalCaseResponse":
        return cls(
            case_id=detail.case_id,
            trace_run_id=detail.trace_run_id,
            workflow_succeeded=detail.workflow_succeeded,
            passed=detail.passed,
            missing_requirements=list(detail.missing_requirements),
            wrong_importance=list(detail.wrong_importance),
            observed_forbidden_capabilities=list(
                detail.observed_forbidden_capabilities
            ),
            actual_requirements=list(detail.actual_requirements),
            error=detail.error,
        )


class RequirementEvalComparisonResponse(CamelCaseModel):
    baseline_run_id: str
    case_pass_rate_delta: float
    workflow_success_rate_delta: float
    capability_recall_delta: float
    importance_accuracy_delta: float
    forbidden_capability_rate_delta: float

    @classmethod
    def from_comparison(
        cls, comparison: RequirementEvalMetricComparison
    ) -> "RequirementEvalComparisonResponse":
        return cls(**asdict(comparison))


class RequirementEvalReviewRequest(CamelCaseModel):
    decision: RequirementEvalReviewDecision
    reviewer: str
    notes: str


class RequirementEvalReviewResponse(CamelCaseModel):
    id: str
    eval_run_id: str
    decision: RequirementEvalReviewDecision
    reviewer: str
    notes: str
    reviewed_at: datetime

    @classmethod
    def from_detail(
        cls, detail: RequirementEvalReviewDetail
    ) -> "RequirementEvalReviewResponse":
        return cls(**asdict(detail))


class AcceptedRequirementEvalBaselineResponse(CamelCaseModel):
    review: RequirementEvalReviewResponse
    run: RequirementEvalRunSummaryResponse

    @classmethod
    def from_baseline(
        cls, baseline: AcceptedRequirementEvalBaseline
    ) -> "AcceptedRequirementEvalBaselineResponse":
        return cls(
            review=RequirementEvalReviewResponse.from_detail(baseline.review),
            run=RequirementEvalRunSummaryResponse.from_summary(baseline.run),
        )


class RequirementEvalRunDetailResponse(CamelCaseModel):
    summary: RequirementEvalRunSummaryResponse
    cases: list[RequirementEvalCaseResponse]
    comparison: RequirementEvalComparisonResponse | None
    review: RequirementEvalReviewResponse | None

    @classmethod
    def from_detail(
        cls, detail: RequirementEvalRunDetail
    ) -> "RequirementEvalRunDetailResponse":
        return cls(
            summary=RequirementEvalRunSummaryResponse.from_summary(detail.summary),
            cases=[RequirementEvalCaseResponse.from_detail(item) for item in detail.cases],
            comparison=(
                RequirementEvalComparisonResponse.from_comparison(detail.comparison)
                if detail.comparison
                else None
            ),
            review=(
                RequirementEvalReviewResponse.from_detail(detail.review)
                if detail.review
                else None
            ),
        )


class RequirementEvalRunPageResponse(CamelCaseModel):
    total: int
    limit: int
    offset: int
    items: list[RequirementEvalRunSummaryResponse]

    @classmethod
    def from_page(
        cls, page: RequirementEvalRunPage
    ) -> "RequirementEvalRunPageResponse":
        return cls(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            items=[
                RequirementEvalRunSummaryResponse.from_summary(item)
                for item in page.items
            ],
        )
