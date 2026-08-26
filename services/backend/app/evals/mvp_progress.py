"""Small engineering progress summary for the JobLens MVP value loop."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.job_requirements.validation import SEMANTIC_POLICY_VERSION
from app.evals.mvp_quality import MvpQualityStatus
from app.workflows.job_requirement_extraction import EXTRACTOR_VERSION

FROZEN_MVP_EXTRACTOR_VERSION = "requirement-extractor-v42.95"
FROZEN_MVP_SEMANTIC_POLICY_VERSION = "requirement-semantics-v42.95"


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
    next_priority: str


def build_mvp_progress_summary(status: MvpQualityStatus) -> MvpProgressSummary:
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
        next_priority=(
            "collect_real_match_reports_and_feedback"
            if status.gate_passed and top_n_available and extraction_frozen
            else "restore_offline_mvp_gate"
        ),
    )
