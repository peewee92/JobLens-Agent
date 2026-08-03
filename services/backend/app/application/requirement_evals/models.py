"""Application read/write models for persisted Requirement Eval runs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class RequirementEvalCaseWrite:
    case_id: str
    trace_run_id: str | None
    workflow_succeeded: bool
    passed: bool
    missing_requirements: tuple[str, ...]
    wrong_importance: tuple[str, ...]
    observed_forbidden_capabilities: tuple[str, ...]
    actual_requirements: tuple[str, ...]
    error: str | None


@dataclass(frozen=True, slots=True)
class RequirementEvalRunWrite:
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
    capability_recall: float
    importance_accuracy: float
    forbidden_capability_rate: float
    gate_passed: bool
    release_eligible: bool
    cases: tuple[RequirementEvalCaseWrite, ...]


@dataclass(frozen=True, slots=True)
class RequirementEvalRunSummary:
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


@dataclass(frozen=True, slots=True)
class RequirementEvalCaseDetail:
    case_id: str
    trace_run_id: str | None
    workflow_succeeded: bool
    passed: bool
    missing_requirements: tuple[str, ...]
    wrong_importance: tuple[str, ...]
    observed_forbidden_capabilities: tuple[str, ...]
    actual_requirements: tuple[str, ...]
    error: str | None


@dataclass(frozen=True, slots=True)
class RequirementEvalMetricComparison:
    baseline_run_id: str
    case_pass_rate_delta: float
    workflow_success_rate_delta: float
    capability_recall_delta: float
    importance_accuracy_delta: float
    forbidden_capability_rate_delta: float


class RequirementEvalReviewDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RequirementEvalReviewWrite:
    review_id: str
    eval_run_id: str
    decision: RequirementEvalReviewDecision
    reviewer: str
    notes: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class RequirementEvalReviewDetail:
    id: str
    eval_run_id: str
    decision: RequirementEvalReviewDecision
    reviewer: str
    notes: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class RequirementEvalRunDetail:
    summary: RequirementEvalRunSummary
    cases: tuple[RequirementEvalCaseDetail, ...]
    comparison: RequirementEvalMetricComparison | None
    review: RequirementEvalReviewDetail | None


@dataclass(frozen=True, slots=True)
class AcceptedRequirementEvalBaseline:
    review: RequirementEvalReviewDetail
    run: RequirementEvalRunSummary


@dataclass(frozen=True, slots=True)
class RequirementEvalRunPage:
    total: int
    limit: int
    offset: int
    items: tuple[RequirementEvalRunSummary, ...]
