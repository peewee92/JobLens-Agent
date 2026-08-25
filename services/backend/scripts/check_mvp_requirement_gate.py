"""Run the default offline-first MVP Requirement quality gate.

The deterministic offline replay is the blocking signal. Live Provider health is
optional diagnostic smoke only and never changes the MVP gate decision.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from collections.abc import Callable
from typing import Any

from app.core.config import get_settings
from scripts.check_requirement_provider_health import check_requirement_provider_health
from scripts.run_requirement_replay_gate import run_offline_requirement_replay_gate


@dataclass(frozen=True)
class MvpRequirementGateResult:
    gate_passed: bool
    replay_passed: bool
    replay_passed_cases: int
    replay_total_cases: int
    provider_smoke_state: str
    provider_smoke_ready: bool | None
    provider_smoke_blocking: bool
    provider_smoke_blocker: str | None
    provider_calls: int


def check_mvp_requirement_gate(
    *,
    replay_runner: Callable[[], Any] = run_offline_requirement_replay_gate,
    include_provider_smoke: bool = False,
    provider_smoke_runner: Callable[[], Any] | None = None,
) -> MvpRequirementGateResult:
    """Evaluate the MVP gate with offline replay as the only blocking signal."""
    replay = replay_runner()
    replay_passed = bool(replay.gate_passed)

    if not include_provider_smoke:
        return MvpRequirementGateResult(
            gate_passed=replay_passed,
            replay_passed=replay_passed,
            replay_passed_cases=int(replay.passed_cases),
            replay_total_cases=int(replay.total_cases),
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
        gate_passed=replay_passed,
        replay_passed=replay_passed,
        replay_passed_cases=int(replay.passed_cases),
        replay_total_cases=int(replay.total_cases),
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
            "MVP Requirement gate "
            f"gatePassed={result.gate_passed} "
            f"replay={result.replay_passed_cases}/{result.replay_total_cases} "
            f"providerSmoke={result.provider_smoke_state} "
            f"providerSmokeBlocking={result.provider_smoke_blocking} "
            f"providerCalls={result.provider_calls}"
        )
    return 0 if result.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
