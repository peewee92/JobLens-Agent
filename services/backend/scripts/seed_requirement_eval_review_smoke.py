"""Seed deterministic Requirement Eval runs for the Web review smoke test.

This utility is restricted to APP_ENV=test and fixed temporary identifiers.
It is not a production data-management command.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.db.models import (
    RequirementEvalCaseResultORM,
    RequirementEvalRunORM,
    TraceSpanORM,
)
from app.db.models.common import utc_now
from app.db.session import SessionLocal

FIXTURE_RUN_ID = "reqeval_fixture_smoke"
FAILED_LIVE_RUN_ID = "reqeval_live_failed_smoke"
ELIGIBLE_LIVE_RUN_ID = "reqeval_live_eligible_smoke"


def _trace(trace_id: str, *, model: str) -> TraceSpanORM:
    return TraceSpanORM(
        id=trace_id,
        capability="requirement_extraction",
        version="requirement-extractor-v1",
        model=model,
        prompt_version="requirement-extraction-v1",
        input_refs={
            "jobId": "job_smoke",
            "descriptionSha256": "smoke-hash",
            "characterCount": 180,
        },
        output={"requirements": [{"normalizedCapability": "Python"}]},
        latency_ms=12,
        input_tokens=20,
        output_tokens=10,
        error=None,
    )


def _run(
    *,
    run_id: str,
    mode: str,
    provider: str,
    model: str,
    passed: bool,
    release_eligible: bool,
    trace_id: str,
) -> RequirementEvalRunORM:
    run = RequirementEvalRunORM(
        id=run_id,
        dataset_version="requirement-extraction-v1",
        mode=mode,
        provider=provider,
        model=model,
        extractor_version="requirement-extractor-v1",
        prompt_version="requirement-extraction-v1",
        gate_version="requirement-eval-gate-v1",
        baseline_run_id=None,
        total_cases=1,
        passed_cases=1 if passed else 0,
        case_pass_rate=1.0 if passed else 0.0,
        workflow_success_rate=1.0,
        capability_recall=1.0 if passed else 0.0,
        importance_accuracy=1.0 if passed else 0.0,
        forbidden_capability_rate=0.0,
        gate_passed=passed,
        release_eligible=release_eligible,
        created_at=utc_now(),
    )
    run.cases.append(
        RequirementEvalCaseResultORM(
            case_id="smoke-case",
            trace_run_id=trace_id,
            workflow_succeeded=True,
            passed=passed,
            missing_requirements=[] if passed else ["skill:Python:must_have"],
            wrong_importance=[] if passed else ["experience:3 years:must_have"],
            observed_forbidden_capabilities=[],
            actual_requirements=["skill:Python:must_have"] if passed else [],
            error=None,
        )
    )
    return run


def main() -> int:
    settings = get_settings()
    if settings.app_env != "test":
        print("Refusing to seed Requirement Eval smoke data outside APP_ENV=test.")
        return 1

    traces = [
        _trace("run_req_fixture_smoke", model="fixture-requirement-extractor"),
        _trace("run_req_live_failed_smoke", model="simulated-live-failed"),
        _trace("run_req_live_eligible_smoke", model="simulated-live-eligible"),
    ]
    runs = [
        _run(
            run_id=FIXTURE_RUN_ID,
            mode="fixture",
            provider="fixture",
            model="fixture-requirement-extractor",
            passed=True,
            release_eligible=False,
            trace_id="run_req_fixture_smoke",
        ),
        _run(
            run_id=FAILED_LIVE_RUN_ID,
            mode="live",
            provider="simulated-live",
            model="simulated-live-failed",
            passed=False,
            release_eligible=False,
            trace_id="run_req_live_failed_smoke",
        ),
        _run(
            run_id=ELIGIBLE_LIVE_RUN_ID,
            mode="live",
            provider="simulated-live",
            model="simulated-live-eligible",
            passed=True,
            release_eligible=True,
            trace_id="run_req_live_eligible_smoke",
        ),
    ]
    with SessionLocal() as session:
        session.add_all([*traces, *runs])
        session.commit()
    print("Seeded fixture, failed-live and eligible-live Requirement Eval runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
