"""Run the deterministic MVP Requirement replay gate without any live Provider."""
from __future__ import annotations

from pathlib import Path

from app.db.session import SessionLocal
from app.evals import load_job_requirement_eval_cases, run_job_requirement_eval
from app.llm import FixtureJobRequirementExtractor
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows import ExtractJobRequirementsWorkflow

DATASET_VERSION = "requirement-extraction-v2"
DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "requirement-extraction"
    / f"{DATASET_VERSION}.jsonl"
)


def run_offline_requirement_replay_gate(*, session_factory=SessionLocal):
    """Evaluate the frozen replay fixture with zero live Provider dependencies."""
    workflow = ExtractJobRequirementsWorkflow(
        FixtureJobRequirementExtractor(),
        lambda: SqlAlchemyTraceUnitOfWork(session_factory),
    )
    return run_job_requirement_eval(
        workflow=workflow,
        cases=load_job_requirement_eval_cases(DATASET),
        dataset_version=DATASET_VERSION,
    )


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
