"""Run the default offline-first MVP quality gate.

Deterministic Requirement replay and the offline Match/Ranking Top-N demo are the
blocking signals. Live Provider health is optional diagnostic smoke only and
never changes the MVP gate decision.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from collections.abc import Callable
from pathlib import Path
import tempfile
from typing import Any

from app.core.config import get_settings
from scripts.check_requirement_provider_health import check_requirement_provider_health
from scripts.run_offline_match_demo import run_demo
from scripts.run_requirement_replay_gate import run_offline_requirement_replay_gate


@dataclass(frozen=True)
class MvpRequirementGateResult:
    gate_passed: bool
    replay_passed: bool
    replay_passed_cases: int
    replay_total_cases: int
    match_demo_passed: bool
    match_demo_persisted_reports: int
    match_demo_top_jobs: int
    match_demo_evidence_complete: bool
    provider_smoke_state: str
    provider_smoke_ready: bool | None
    provider_smoke_blocking: bool
    provider_smoke_blocker: str | None
    provider_calls: int


def _run_offline_match_demo() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="joblens-mvp-gate-") as directory:
        return run_demo(database_path=Path(directory) / "match-demo.db", top_n=5)


def check_mvp_requirement_gate(
    *,
    replay_runner: Callable[[], Any] = run_offline_requirement_replay_gate,
    match_demo_runner: Callable[[], dict[str, object]] = _run_offline_match_demo,
    include_provider_smoke: bool = False,
    provider_smoke_runner: Callable[[], Any] | None = None,
) -> MvpRequirementGateResult:
    """Evaluate the MVP gate from deterministic offline value-loop signals."""
    replay = replay_runner()
    replay_passed = bool(replay.gate_passed)

    match_demo = match_demo_runner()
    persisted_reports = int(match_demo.get("persistedMatchReports", 0))
    top_jobs = tuple(match_demo.get("topJobs", ()))
    evidence_complete = bool(top_jobs) and all(
        isinstance(item, dict) and bool(item.get("evidenceLinks")) for item in top_jobs
    )
    match_demo_passed = (
        int(match_demo.get("externalProviderCalls", -1)) == 0
        and persisted_reports >= 20
        and len(top_jobs) == 5
        and evidence_complete
    )
    gate_passed = replay_passed and match_demo_passed

    if not include_provider_smoke:
        return MvpRequirementGateResult(
            gate_passed=gate_passed,
            replay_passed=replay_passed,
            replay_passed_cases=int(replay.passed_cases),
            replay_total_cases=int(replay.total_cases),
            match_demo_passed=match_demo_passed,
            match_demo_persisted_reports=persisted_reports,
            match_demo_top_jobs=len(top_jobs),
            match_demo_evidence_complete=evidence_complete,
            provider_smoke_state="not_requested",
            provider_smoke_ready=None,
            provider_smoke_blocking=False,
            provider_smoke_blocker=None,
            provider_calls=0,
        )

    if provider_smoke_runner is None:
        raise ValueError("provider_smoke_runner is required when Provider smoke is enabled")

    health = provider_smoke_runner()
    return MvpRequirementGateResult(
        gate_passed=gate_passed,
        replay_passed=replay_passed,
        replay_passed_cases=int(replay.passed_cases),
        replay_total_cases=int(replay.total_cases),
        match_demo_passed=match_demo_passed,
        match_demo_persisted_reports=persisted_reports,
        match_demo_top_jobs=len(top_jobs),
        match_demo_evidence_complete=evidence_complete,
        provider_smoke_state=str(health.state),
        provider_smoke_ready=bool(health.ready_for_requirement_live_run),
        provider_smoke_blocking=False,
        provider_smoke_blocker=health.blocker,
        provider_calls=int(health.provider_calls),
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider-smoke",
        action="store_true",
        help="Also run the live Provider health smoke. This is non-blocking.",
    )
    parser.add_argument(
        "--confirm-live-cost",
        action="store_true",
        help="Acknowledge that Provider smoke can perform up to two billed calls.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _serialize(result: MvpRequirementGateResult) -> dict[str, Any]:
    payload = asdict(result)
    return {
        "gatePassed": payload["gate_passed"],
        "replayPassed": payload["replay_passed"],
        "replayPassedCases": payload["replay_passed_cases"],
        "replayTotalCases": payload["replay_total_cases"],
        "matchDemoPassed": payload["match_demo_passed"],
        "matchDemoPersistedReports": payload["match_demo_persisted_reports"],
        "matchDemoTopJobs": payload["match_demo_top_jobs"],
        "matchDemoEvidenceComplete": payload["match_demo_evidence_complete"],
        "providerSmokeState": payload["provider_smoke_state"],
        "providerSmokeReady": payload["provider_smoke_ready"],
        "providerSmokeBlocking": payload["provider_smoke_blocking"],
        "providerSmokeBlocker": payload["provider_smoke_blocker"],
        "providerCalls": payload["provider_calls"],
    }


def main() -> int:
    args = _arguments()
    if args.provider_smoke and not args.confirm_live_cost:
        print("Provider smoke requires --confirm-live-cost because it can perform billed calls.")
        return 2

    smoke_runner = None
    if args.provider_smoke:
        settings = get_settings()
        smoke_runner = lambda: check_requirement_provider_health(
            settings=settings,
            execute_health_probe=True,
            confirm_live_cost=True,
        )

    result = check_mvp_requirement_gate(
        include_provider_smoke=args.provider_smoke,
        provider_smoke_runner=smoke_runner,
    )
    payload = _serialize(result)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "MVP quality gate "
            f"gatePassed={result.gate_passed} "
            f"replay={result.replay_passed_cases}/{result.replay_total_cases} "
            f"matchDemo={result.match_demo_top_jobs}/5 "
            f"providerSmoke={result.provider_smoke_state} "
            f"providerSmokeBlocking={result.provider_smoke_blocking} "
            f"providerCalls={result.provider_calls}"
        )
    return 0 if result.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
