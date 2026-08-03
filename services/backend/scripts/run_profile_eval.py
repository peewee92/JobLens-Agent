"""Run, gate and persist the Profile Extraction evaluation dataset."""
from __future__ import annotations

import argparse
from pathlib import Path

from app.application.profile_evals import ProfileEvalRunNotFoundError
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.evals import ProfileEvalMode, RunProfileEvalUseCase, load_profile_eval_cases
from app.llm import build_profile_extractor
from app.repositories import (
    SqlAlchemyProfileEvalQueryRepository,
    SqlAlchemyProfileEvalUnitOfWork,
    SqlAlchemyTraceUnitOfWork,
)
from app.workflows import ProposeProfileFromResumeWorkflow

DATASET_VERSION = "profile-extraction-v1"
DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "profile-extraction"
    / f"{DATASET_VERSION}.jsonl"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run-id")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    settings = get_settings()
    provider = settings.profile_extractor_provider.strip().lower()
    if provider == "fixture":
        mode = ProfileEvalMode.FIXTURE
    elif provider == "openai":
        mode = ProfileEvalMode.LIVE
    else:
        print(
            "Profile Eval requires PROFILE_EXTRACTOR_PROVIDER=fixture or openai; "
            f"received {provider!r}."
        )
        return 1

    extractor = build_profile_extractor(settings)
    workflow = ProposeProfileFromResumeWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(SessionLocal),
    )
    query_repository = SqlAlchemyProfileEvalQueryRepository(SessionLocal)
    try:
        detail = RunProfileEvalUseCase(
            workflow=workflow,
            eval_uow_factory=lambda: SqlAlchemyProfileEvalUnitOfWork(SessionLocal),
            query_repository=query_repository,
            dataset_version=DATASET_VERSION,
            mode=mode,
            provider=provider,
            model=extractor.model_name,
        ).execute(
            load_profile_eval_cases(DATASET),
            baseline_run_id=args.baseline_run_id,
        )
    except ProfileEvalRunNotFoundError as error:
        print(str(error))
        return 1
    summary = detail.summary
    print(
        f"Profile Eval id={summary.id} mode={summary.mode} "
        f"provider={summary.provider} model={summary.model} "
        f"passed={summary.passed_cases}/{summary.total_cases} "
        f"caseRate={summary.case_pass_rate:.2%} "
        f"skillRecall={summary.skill_recall:.2%} "
        f"gatePassed={summary.gate_passed} "
        f"releaseEligible={summary.release_eligible}"
    )
    if detail.comparison:
        comparison = detail.comparison
        print(
            f"Baseline {comparison.baseline_run_id}: "
            f"caseRateDelta={comparison.case_pass_rate_delta:+.2%} "
            f"skillRecallDelta={comparison.skill_recall_delta:+.2%} "
            f"forbiddenFactRateDelta={comparison.forbidden_fact_rate_delta:+.2%}"
        )
    for case in detail.cases:
        if not case.passed:
            print(
                f"- {case.case_id} trace={case.trace_run_id or 'none'}: "
                f"{'; '.join(case.failure_reasons)}"
            )
    if summary.mode == ProfileEvalMode.FIXTURE.value:
        print(
            "Fixture gate result validates the evaluation pipeline only; "
            "it does not qualify a live model for release."
        )
    return 0 if summary.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
