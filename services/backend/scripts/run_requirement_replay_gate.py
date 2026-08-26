"""Run the deterministic MVP Requirement replay gate without any live Provider."""
from __future__ import annotations

from app.db.session import SessionLocal
from app.evals.mvp_quality import (
    REQUIREMENT_REPLAY_DATASET as DATASET,
    REQUIREMENT_REPLAY_DATASET_VERSION as DATASET_VERSION,
    run_offline_requirement_replay_gate as _run_offline_requirement_replay_gate,
)


def run_offline_requirement_replay_gate(*, session_factory=SessionLocal):
    """Evaluate the frozen replay fixture with zero live Provider dependencies."""
    return _run_offline_requirement_replay_gate(session_factory=session_factory)


def main() -> int:
    report = run_offline_requirement_replay_gate()
    print(
        "MVP Requirement replay gate "
        f"passed={report.passed_cases}/{report.total_cases} "
        f"caseRate={report.case_pass_rate:.2%} "
        f"workflowRate={report.workflow_success_rate:.2%} "
        f"capabilityRecall={report.capability_recall:.2%} "
        f"importanceAccuracy={report.importance_accuracy:.2%} "
        f"forbiddenRate={report.forbidden_capability_rate:.2%} "
        f"gatePassed={report.gate_passed} providerCalls=0"
    )
    return 0 if report.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
