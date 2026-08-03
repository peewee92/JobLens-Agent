"""Run the versioned Job Requirement Extraction evaluation dataset."""
from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.evals import load_job_requirement_eval_cases, run_job_requirement_eval
from app.llm import build_job_requirement_extractor
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows import ExtractJobRequirementsWorkflow

DATASET_VERSION = "requirement-extraction-v1"
DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "requirement-extraction"
    / f"{DATASET_VERSION}.jsonl"
)


def main() -> int:
    settings = get_settings()
    provider = settings.requirement_extractor_provider.strip().casefold()
    if provider not in {"fixture", "openai"}:
        print(
            "Requirement Eval requires REQUIREMENT_EXTRACTOR_PROVIDER=fixture or openai; "
            f"received {provider!r}."
        )
        return 1
    extractor = build_job_requirement_extractor(settings)
    workflow = ExtractJobRequirementsWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(SessionLocal),
    )
    report = run_job_requirement_eval(
        workflow=workflow,
        cases=load_job_requirement_eval_cases(DATASET),
        dataset_version=DATASET_VERSION,
    )
    print(
        f"Requirement Eval provider={provider} model={extractor.model_name} "
        f"passed={report.passed_cases}/{report.total_cases} "
        f"caseRate={report.case_pass_rate:.2%} "
        f"workflowRate={report.workflow_success_rate:.2%} "
        f"capabilityRecall={report.capability_recall:.2%} "
        f"importanceAccuracy={report.importance_accuracy:.2%} "
        f"forbiddenRate={report.forbidden_capability_rate:.2%} "
        f"gatePassed={report.gate_passed}"
    )
    for case in report.cases:
        if not case.passed:
            details = [*case.missing_requirements, *case.wrong_importance]
            details.extend(case.observed_forbidden_capabilities)
            if case.error:
                details.append(case.error)
            print(
                f"- {case.case_id} trace={case.trace_run_id or 'none'}: "
                f"{'; '.join(details) or 'unknown failure'}"
            )
    if provider == "fixture":
        print(
            "Fixture Requirement Eval validates the pipeline only; "
            "it does not qualify a live model for release."
        )
    return 0 if report.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
