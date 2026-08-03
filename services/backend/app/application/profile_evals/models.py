"""Application read/write models for persisted Profile Eval runs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class ProfileEvalCaseWrite:
    case_id: str
    trace_run_id: str | None
    workflow_succeeded: bool
    passed: bool
    failure_codes: tuple[str, ...]
    failure_reasons: tuple[str, ...]
    expected_skills: tuple[str, ...]
    actual_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    expected_years: float | None
    actual_years: float | None
    forbidden_terms: tuple[str, ...]
    observed_forbidden_terms: tuple[str, ...]
    diagnostics: dict[str, object]


@dataclass(frozen=True, slots=True)
class ProfileEvalRunWrite:
    eval_run_id: str
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
    cases: tuple[ProfileEvalCaseWrite, ...]


@dataclass(frozen=True, slots=True)
class ProfileEvalRunSummary:
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


@dataclass(frozen=True, slots=True)
class ProfileEvalCaseDetail:
    case_id: str
    trace_run_id: str | None
    workflow_succeeded: bool
    passed: bool
    failure_codes: tuple[str, ...]
    failure_reasons: tuple[str, ...]
    expected_skills: tuple[str, ...]
    actual_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    expected_years: float | None
    actual_years: float | None
    forbidden_terms: tuple[str, ...]
    observed_forbidden_terms: tuple[str, ...]
    diagnostics: dict[str, object]


@dataclass(frozen=True, slots=True)
class ProfileEvalMetricComparison:
    baseline_run_id: str
    case_pass_rate_delta: float
    workflow_success_rate_delta: float
    skill_recall_delta: float
    years_accuracy_delta: float | None
    forbidden_fact_rate_delta: float


class ProfileEvalReviewDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ProfileEvalReviewWrite:
    review_id: str
    eval_run_id: str
    decision: ProfileEvalReviewDecision
    reviewer: str
    notes: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class ProfileEvalReviewDetail:
    id: str
    eval_run_id: str
    decision: ProfileEvalReviewDecision
    reviewer: str
    notes: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class ProfileEvalRunDetail:
    summary: ProfileEvalRunSummary
    cases: tuple[ProfileEvalCaseDetail, ...]
    comparison: ProfileEvalMetricComparison | None
    review: ProfileEvalReviewDetail | None


@dataclass(frozen=True, slots=True)
class AcceptedProfileEvalBaseline:
    review: ProfileEvalReviewDetail
    run: ProfileEvalRunSummary


@dataclass(frozen=True, slots=True)
class ProfileEvalRunPage:
    total: int
    limit: int
    offset: int
    items: tuple[ProfileEvalRunSummary, ...]
