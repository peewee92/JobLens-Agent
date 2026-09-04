"""Small engineering progress summary for the JobLens MVP value loop."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.job_requirements.validation import SEMANTIC_POLICY_VERSION
from app.evals.mvp_quality import MvpQualityStatus
from app.workflows.job_requirement_extraction import EXTRACTOR_VERSION

FROZEN_MVP_EXTRACTOR_VERSION = "requirement-extractor-v42.96"
FROZEN_MVP_SEMANTIC_POLICY_VERSION = "requirement-semantics-v42.96"


@dataclass(frozen=True, slots=True)
class RealMvpLoopProgress:
    total_jobs: int
    current_match_reports: int
    feedback_covered_reports: int
    requirement_analysis_needed: int
    match_ready_without_report: int


@dataclass(frozen=True, slots=True)
class RequirementRevalidationProgress:
    run_id: str
    status: str
    completed_case_count: int
    attempted_calls: int
    canary_decision: str | None
    semantic_policy_version: str | None


@dataclass(frozen=True, slots=True)
class RequirementReviewProgress:
    sample_size: int
    reviewed_count: int
    accepted_count: int
    rejected_count: int
    final_decision: str | None
    match_release_eligible: bool
    issue_code_counts: dict[str, int]
    semantic_policy_version: str | None
    extractor_version: str = EXTRACTOR_VERSION


@dataclass(frozen=True, slots=True)
class MvpProgressSummary:
    mvp_gate_passed: bool
    offline_e2e_slices_completed: int
    offline_e2e_slices_total: int
    top_n_available: bool
    top_n_jobs: int
    top_n_evidence_complete: bool
    extraction_version: str
    semantic_policy_version: str
    extraction_frozen: bool
    provider_smoke_blocking: bool
    real_loop_data_available: bool
    real_total_jobs: int | None
    real_current_match_reports: int | None
    real_feedback_covered_reports: int | None
    real_requirement_analysis_needed: int | None
    real_match_ready_without_report: int | None
    real_match_report_coverage: float | None
    real_feedback_coverage: float | None
    requirement_revalidation_data_available: bool
    requirement_revalidation_run_id: str | None
    requirement_revalidation_status: str | None
    requirement_revalidation_completed_case_count: int | None
    requirement_revalidation_attempted_calls: int | None
    requirement_revalidation_canary_decision: str | None
    requirement_revalidation_semantic_policy_version: str | None
    requirement_review_data_available: bool
    requirement_review_sample_size: int | None
    requirement_review_reviewed_count: int | None
    requirement_review_accepted_count: int | None
    requirement_review_rejected_count: int | None
    requirement_review_final_decision: str | None
    requirement_review_match_release_eligible: bool | None
    requirement_review_issue_code_counts: dict[str, int] | None
    requirement_review_semantic_policy_version: str | None
    requirement_review_extractor_version: str | None
    next_priority: str


def build_mvp_progress_summary(
    status: MvpQualityStatus,
    *,
    real_loop: RealMvpLoopProgress | None = None,
    requirement_revalidation: RequirementRevalidationProgress | None = None,
    requirement_review: RequirementReviewProgress | None = None,
) -> MvpProgressSummary:
    """Translate quality facts into the small set of progress metrics MVP cares about."""
    top_n_available = (
        status.match_demo_passed
        and status.match_demo_top_jobs == 5
        and status.match_demo_evidence_complete
    )
    extraction_frozen = (
        EXTRACTOR_VERSION == FROZEN_MVP_EXTRACTOR_VERSION
        and SEMANTIC_POLICY_VERSION == FROZEN_MVP_SEMANTIC_POLICY_VERSION
    )
    real_match_report_coverage = (
        real_loop.current_match_reports / real_loop.total_jobs
        if real_loop is not None and real_loop.total_jobs > 0
        else None
    )
    real_feedback_coverage = (
        real_loop.feedback_covered_reports / real_loop.current_match_reports
        if real_loop is not None and real_loop.current_match_reports > 0
        else None
    )
    offline_ready = status.gate_passed and top_n_available and extraction_frozen
    real_loop_observed = (
        real_loop is not None
        and real_loop.total_jobs > 0
        and real_loop.current_match_reports >= real_loop.total_jobs
        and real_loop.feedback_covered_reports >= real_loop.current_match_reports
    )
    current_revalidation = (
        requirement_revalidation is not None
        and requirement_revalidation.semantic_policy_version == SEMANTIC_POLICY_VERSION
    )
    if not offline_ready:
        next_priority = "restore_offline_mvp_gate"
    elif requirement_review is not None and requirement_review.sample_size == 20:
        if requirement_review.reviewed_count < requirement_review.sample_size:
            next_priority = "complete_requirement_review_cases"
        elif requirement_review.final_decision is None:
            # Human evidence must be closed before local extractor/semantic version drift
            # can route the project into another revalidation cycle. Otherwise a code
            # bump can bypass an already completed 20-case review's immutable Final
            # Decision gate.
            next_priority = "complete_requirement_review_final_decision"
        elif (
            requirement_review.extractor_version != EXTRACTOR_VERSION
            or requirement_review.semantic_policy_version != SEMANTIC_POLICY_VERSION
        ):
            next_priority = "revalidate_requirement_quality"
        elif requirement_review.final_decision == "reject_for_match":
            next_priority = "remediate_requirement_quality"
        elif not requirement_review.match_release_eligible:
            next_priority = "restore_requirement_match_release"
        elif real_loop_observed:
            next_priority = "real_mvp_value_loop_observed"
        elif real_loop is None:
            next_priority = "collect_real_match_reports_and_feedback"
        elif real_loop.feedback_covered_reports < real_loop.current_match_reports:
            next_priority = "complete_current_user_feedback"
        elif real_loop.match_ready_without_report > 0:
            next_priority = "generate_ready_match_reports"
        elif real_loop.requirement_analysis_needed > 0:
            next_priority = "expand_real_match_report_coverage"
        else:
            next_priority = "resolve_real_match_input_blockers"
    elif current_revalidation:
        assert requirement_revalidation is not None
        if requirement_revalidation.status == "awaiting_canary_review":
            next_priority = "complete_requirement_revalidation_canary_review"
        elif requirement_revalidation.status == "stopped":
            next_priority = "remediate_requirement_quality"
        elif (
            requirement_revalidation.canary_decision == "continue"
            and requirement_revalidation.completed_case_count < 20
        ):
            next_priority = "resume_requirement_revalidation"
        elif requirement_revalidation.completed_case_count < 20:
            next_priority = "continue_requirement_revalidation_canary"
        else:
            next_priority = "complete_requirement_review_cases"
    elif real_loop_observed:
        next_priority = "real_mvp_value_loop_observed"
    elif real_loop is None:
        next_priority = "collect_real_match_reports_and_feedback"
    elif real_loop.feedback_covered_reports < real_loop.current_match_reports:
        next_priority = "complete_current_user_feedback"
    elif real_loop.match_ready_without_report > 0:
        next_priority = "generate_ready_match_reports"
    elif real_loop.requirement_analysis_needed > 0:
        next_priority = "expand_real_match_report_coverage"
    else:
        next_priority = "resolve_real_match_input_blockers"
    return MvpProgressSummary(
        mvp_gate_passed=status.gate_passed,
        offline_e2e_slices_completed=1 if top_n_available else 0,
        offline_e2e_slices_total=1,
        top_n_available=top_n_available,
        top_n_jobs=status.match_demo_top_jobs,
        top_n_evidence_complete=status.match_demo_evidence_complete,
        extraction_version=EXTRACTOR_VERSION,
        semantic_policy_version=SEMANTIC_POLICY_VERSION,
        extraction_frozen=extraction_frozen,
        provider_smoke_blocking=status.provider_smoke_blocking,
        real_loop_data_available=real_loop is not None,
        real_total_jobs=real_loop.total_jobs if real_loop is not None else None,
        real_current_match_reports=(
            real_loop.current_match_reports if real_loop is not None else None
        ),
        real_feedback_covered_reports=(
            real_loop.feedback_covered_reports if real_loop is not None else None
        ),
        real_requirement_analysis_needed=(
            real_loop.requirement_analysis_needed if real_loop is not None else None
        ),
        real_match_ready_without_report=(
            real_loop.match_ready_without_report if real_loop is not None else None
        ),
        real_match_report_coverage=real_match_report_coverage,
        real_feedback_coverage=real_feedback_coverage,
        requirement_revalidation_data_available=requirement_revalidation is not None,
        requirement_revalidation_run_id=(
            requirement_revalidation.run_id if requirement_revalidation is not None else None
        ),
        requirement_revalidation_status=(
            requirement_revalidation.status if requirement_revalidation is not None else None
        ),
        requirement_revalidation_completed_case_count=(
            requirement_revalidation.completed_case_count
            if requirement_revalidation is not None
            else None
        ),
        requirement_revalidation_attempted_calls=(
            requirement_revalidation.attempted_calls
            if requirement_revalidation is not None
            else None
        ),
        requirement_revalidation_canary_decision=(
            requirement_revalidation.canary_decision
            if requirement_revalidation is not None
            else None
        ),
        requirement_revalidation_semantic_policy_version=(
            requirement_revalidation.semantic_policy_version
            if requirement_revalidation is not None
            else None
        ),
        requirement_review_data_available=requirement_review is not None,
        requirement_review_sample_size=(
            requirement_review.sample_size if requirement_review is not None else None
        ),
        requirement_review_reviewed_count=(
            requirement_review.reviewed_count if requirement_review is not None else None
        ),
        requirement_review_accepted_count=(
            requirement_review.accepted_count if requirement_review is not None else None
        ),
        requirement_review_rejected_count=(
            requirement_review.rejected_count if requirement_review is not None else None
        ),
        requirement_review_final_decision=(
            requirement_review.final_decision if requirement_review is not None else None
        ),
        requirement_review_match_release_eligible=(
            requirement_review.match_release_eligible if requirement_review is not None else None
        ),
        requirement_review_issue_code_counts=(
            dict(requirement_review.issue_code_counts) if requirement_review is not None else None
        ),
        requirement_review_semantic_policy_version=(
            requirement_review.semantic_policy_version if requirement_review is not None else None
        ),
        requirement_review_extractor_version=(
            requirement_review.extractor_version if requirement_review is not None else None
        ),
        next_priority=next_priority,
    )
