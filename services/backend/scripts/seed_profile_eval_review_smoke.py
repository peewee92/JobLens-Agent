"""Seed deterministic Profile Eval runs for the Web review smoke test.

This utility is intentionally restricted to APP_ENV=test and fixed temporary
identifiers. It is not a production data-management command.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.db.models import ProfileEvalCaseResultORM, ProfileEvalRunORM, TraceSpanORM
from app.db.models.common import utc_now
from app.db.session import SessionLocal

FIXTURE_RUN_ID = "eval_fixture_smoke"
FAILED_LIVE_RUN_ID = "eval_live_failed_smoke"
ELIGIBLE_LIVE_RUN_ID = "eval_live_eligible_smoke"


def _trace(trace_id: str, *, model: str, error: str | None = None) -> TraceSpanORM:
    return TraceSpanORM(
        id=trace_id,
        capability="profile_extraction",
        version="profile-extractor-v1",
        model=model,
        prompt_version="profile-proposal-v1",
        input_refs={"resumeSha256": "smoke-hash", "characterCount": 120},
        output=None if error else {"headline": "Smoke profile proposal"},
        latency_ms=12,
        input_tokens=20,
        output_tokens=10,
        error=error,
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
) -> ProfileEvalRunORM:
    run = ProfileEvalRunORM(
        id=run_id,
        dataset_version="profile-extraction-v1",
        mode=mode,
        provider=provider,
        model=model,
        extractor_version="profile-extractor-v1",
        prompt_version="profile-proposal-v1",
        gate_version="profile-eval-gate-v1",
        baseline_run_id=None,
        total_cases=1,
        passed_cases=1 if passed else 0,
        case_pass_rate=1.0 if passed else 0.0,
        workflow_success_rate=1.0,
        skill_recall=1.0 if passed else 0.0,
        years_accuracy=1.0,
        forbidden_fact_rate=0.0,
        gate_passed=passed,
        release_eligible=release_eligible,
        created_at=utc_now(),
    )
    run.cases.append(
        ProfileEvalCaseResultORM(
            case_id="smoke-case",
            trace_run_id=trace_id,
            workflow_succeeded=True,
            passed=passed,
            failure_codes=[] if passed else ["missing_expected_skill"],
            failure_reasons=[] if passed else ["missing expected skill: Agent"],
            expected_skills=["Agent"],
            actual_skills=["Agent"] if passed else [],
            missing_skills=[] if passed else ["Agent"],
            expected_years=3.0,
            actual_years=3.0,
            forbidden_terms=["invented company"],
            observed_forbidden_terms=[],
            diagnostics={"seed": "profile-eval-review-smoke"},
        )
    )
    return run


def main() -> int:
    settings = get_settings()
    if settings.app_env != "test":
        print("Refusing to seed Profile Eval smoke data outside APP_ENV=test.")
        return 1

    traces = [
        _trace("run_fixture_smoke", model="fixture-profile-extractor"),
        _trace("run_live_failed_smoke", model="simulated-live-failed"),
        _trace("run_live_eligible_smoke", model="simulated-live-eligible"),
    ]
    runs = [
        _run(
            run_id=FIXTURE_RUN_ID,
            mode="fixture",
            provider="fixture",
            model="fixture-profile-extractor",
            passed=True,
            release_eligible=False,
            trace_id="run_fixture_smoke",
        ),
        _run(
            run_id=FAILED_LIVE_RUN_ID,
            mode="live",
            provider="simulated-live",
            model="simulated-live-failed",
            passed=False,
            release_eligible=False,
            trace_id="run_live_failed_smoke",
        ),
        _run(
            run_id=ELIGIBLE_LIVE_RUN_ID,
            mode="live",
            provider="simulated-live",
            model="simulated-live-eligible",
            passed=True,
            release_eligible=True,
            trace_id="run_live_eligible_smoke",
        ),
    ]
    with SessionLocal() as session:
        session.add_all([*traces, *runs])
        session.commit()
    print("Seeded fixture, failed-live and eligible-live Profile Eval runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
