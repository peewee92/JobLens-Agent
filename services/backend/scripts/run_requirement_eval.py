"""Run, gate and persist the Job Requirement Extraction evaluation dataset."""
from __future__ import annotations

import argparse
from pathlib import Path

from app.application.requirement_evals import RequirementEvalRunNotFoundError
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.evals import (
    RequirementEvalMode,
    RunRequirementEvalUseCase,
    load_job_requirement_eval_cases,
)
from app.llm import build_job_requirement_extractor
from app.repositories import (
    SqlAlchemyRequirementEvalQueryRepository,
    SqlAlchemyRequirementEvalUnitOfWork,
    SqlAlchemyTraceUnitOfWork,
)
from app.workflows import ExtractJobRequirementsWorkflow

DATASET_VERSION = "requirement-extraction-v2"
DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "requirement-extraction"
    / f"{DATASET_VERSION}.jsonl"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    baseline_group = parser.add_mutually_exclusive_group()
    baseline_group.add_argument("--baseline-run-id")
    baseline_group.add_argument("--accepted-baseline", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    settings = get_settings()
    provider = settings.requirement_extractor_provider.strip().casefold()
    if provider == "fixture":
        mode = RequirementEvalMode.FIXTURE
    elif provider == "openai":
        mode = RequirementEvalMode.LIVE
    else:
        print(
            "Requirement Eval requires REQUIREMENT_EXTRACTOR_PROVIDER=fixture or openai; "
            f"received {provider!r}."
        )
        return 1

    query_repository = SqlAlchemyRequirementEvalQueryRepository(SessionLocal)
    baseline_run_id = args.baseline_run_id
    if args.accepted_baseline:
        if mode is not RequirementEvalMode.LIVE:
            print("--accepted-baseline is only valid for a live Provider Eval.")
            return 1
        accepted_baseline = query_repository.get_accepted_baseline()
        if accepted_baseline is None:
            print("No human-accepted live Requirement Eval baseline exists.")
            return 1
        baseline_run_id = accepted_baseline.run.id
        print(f"Using accepted baseline {baseline_run_id}.")

    extractor = build_job_requirement_extractor(settings)
    workflow = ExtractJobRequirementsWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(SessionLocal),
    )
    try:
        detail = RunRequirementEvalUseCase(
            workflow=workflow,
            eval_uow_factory=lambda: SqlAlchemyRequirementEvalUnitOfWork(
                SessionLocal
            ),
            query_repository=query_repository,
            dataset_version=DATASET_VERSION,
            mode=mode,
            provider=provider,
            model=extractor.model_name,
        ).execute(
            load_job_requirement_eval_cases(DATASET),
            baseline_run_id=baseline_run_id,
        )
    except RequirementEvalRunNotFoundError as error:
        print(str(error))
        return 1

    summary = detail.summary
    print(
        f"Requirement Eval id={summary.id} mode={summary.mode} "
        f"provider={summary.provider} model={summary.model} "
        f"passed={summary.passed_cases}/{summary.total_cases} "
        f"caseRate={summary.case_pass_rate:.2%} "
        f"workflowRate={summary.workflow_success_rate:.2%} "
        f"capabilityRecall={summary.capability_recall:.2%} "
        f"importanceAccuracy={summary.importance_accuracy:.2%} "
        f"forbiddenRate={summary.forbidden_capability_rate:.2%} "
        f"gatePassed={summary.gate_passed} "
        f"releaseEligible={summary.release_eligible}"
    )
    if detail.comparison:
        comparison = detail.comparison
        print(
            f"Baseline {comparison.baseline_run_id}: "
            f"caseRateDelta={comparison.case_pass_rate_delta:+.2%} "
            f"capabilityRecallDelta={comparison.capability_recall_delta:+.2%} "
            f"importanceAccuracyDelta={comparison.importance_accuracy_delta:+.2%} "
            f"forbiddenRateDelta={comparison.forbidden_capability_rate_delta:+.2%}"
        )
    for case in detail.cases:
        if not case.passed:
            details = [*case.missing_requirements, *case.wrong_importance]
            details.extend(case.observed_forbidden_capabilities)
            if case.error:
                details.append(case.error)
            print(
                f"- {case.case_id} trace={case.trace_run_id or 'none'}: "
                f"{'; '.join(details) or 'unknown failure'}"
            )
    if summary.mode == RequirementEvalMode.FIXTURE.value:
        print(
            "Fixture Requirement Eval validates the pipeline only; "
            "it does not qualify a live model for release."
        )
    return 0 if summary.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
