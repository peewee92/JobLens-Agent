"""HTTP response models for persisted Profile Eval runs."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from app.api.v1.schemas.common import CamelCaseModel
from app.application.profile_evals import (
    AcceptedProfileEvalBaseline,
    ProfileEvalCaseDetail,
    ProfileEvalMetricComparison,
    ProfileEvalReviewDecision,
    ProfileEvalReviewDetail,
    ProfileEvalRunDetail,
    ProfileEvalRunPage,
    ProfileEvalRunSummary,
)


class ProfileEvalRunSummaryResponse(CamelCaseModel):
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
    skill_recall: float
    years_accuracy: float | None
    forbidden_fact_rate: float
    gate_passed: bool
    release_eligible: bool
    created_at: datetime

    @classmethod
    def from_summary(
        cls, summary: ProfileEvalRunSummary
    ) -> "ProfileEvalRunSummaryResponse":
        return cls(**asdict(summary))


class ProfileEvalCaseResponse(CamelCaseModel):
    case_id: str
    trace_run_id: str | None
    workflow_succeeded: bool
    passed: bool
    failure_codes: list[str]
    failure_reasons: list[str]
    expected_skills: list[str]
    actual_skills: list[str]
    missing_skills: list[str]
    expected_years: float | None
    actual_years: float | None
    forbidden_terms: list[str]
    observed_forbidden_terms: list[str]
    diagnostics: dict[str, object]

    @classmethod
    def from_detail(cls, detail: ProfileEvalCaseDetail) -> "ProfileEvalCaseResponse":
        return cls(
            case_id=detail.case_id,
            trace_run_id=detail.trace_run_id,
            workflow_succeeded=detail.workflow_succeeded,
            passed=detail.passed,
            failure_codes=list(detail.failure_codes),
            failure_reasons=list(detail.failure_reasons),
            expected_skills=list(detail.expected_skills),
            actual_skills=list(detail.actual_skills),
            missing_skills=list(detail.missing_skills),
            expected_years=detail.expected_years,
            actual_years=detail.actual_years,
            forbidden_terms=list(detail.forbidden_terms),
            observed_forbidden_terms=list(detail.observed_forbidden_terms),
            diagnostics=dict(detail.diagnostics),
        )


class ProfileEvalComparisonResponse(CamelCaseModel):
    baseline_run_id: str
    case_pass_rate_delta: float
    workflow_success_rate_delta: float
    skill_recall_delta: float
    years_accuracy_delta: float | None
    forbidden_fact_rate_delta: float

    @classmethod
    def from_comparison(
        cls, comparison: ProfileEvalMetricComparison
    ) -> "ProfileEvalComparisonResponse":
        return cls(**asdict(comparison))


class ProfileEvalReviewRequest(CamelCaseModel):
    decision: ProfileEvalReviewDecision
    reviewer: str
    notes: str


class ProfileEvalReviewResponse(CamelCaseModel):
    id: str
    eval_run_id: str
    decision: ProfileEvalReviewDecision
    reviewer: str
    notes: str
    reviewed_at: datetime

    @classmethod
    def from_detail(
        cls, detail: ProfileEvalReviewDetail
    ) -> "ProfileEvalReviewResponse":
        return cls(**asdict(detail))


class AcceptedProfileEvalBaselineResponse(CamelCaseModel):
    review: ProfileEvalReviewResponse
    run: ProfileEvalRunSummaryResponse

    @classmethod
    def from_baseline(
        cls, baseline: AcceptedProfileEvalBaseline
    ) -> "AcceptedProfileEvalBaselineResponse":
        return cls(
            review=ProfileEvalReviewResponse.from_detail(baseline.review),
            run=ProfileEvalRunSummaryResponse.from_summary(baseline.run),
        )


class ProfileEvalRunDetailResponse(CamelCaseModel):
    summary: ProfileEvalRunSummaryResponse
    cases: list[ProfileEvalCaseResponse]
    comparison: ProfileEvalComparisonResponse | None
    review: ProfileEvalReviewResponse | None

    @classmethod
    def from_detail(cls, detail: ProfileEvalRunDetail) -> "ProfileEvalRunDetailResponse":
        return cls(
            summary=ProfileEvalRunSummaryResponse.from_summary(detail.summary),
            cases=[ProfileEvalCaseResponse.from_detail(item) for item in detail.cases],
            comparison=(
                ProfileEvalComparisonResponse.from_comparison(detail.comparison)
                if detail.comparison
                else None
            ),
            review=(
                ProfileEvalReviewResponse.from_detail(detail.review)
                if detail.review
                else None
            ),
        )


class ProfileEvalRunPageResponse(CamelCaseModel):
    total: int
    limit: int
    offset: int
    items: list[ProfileEvalRunSummaryResponse]

    @classmethod
    def from_page(cls, page: ProfileEvalRunPage) -> "ProfileEvalRunPageResponse":
        return cls(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            items=[ProfileEvalRunSummaryResponse.from_summary(item) for item in page.items],
        )
