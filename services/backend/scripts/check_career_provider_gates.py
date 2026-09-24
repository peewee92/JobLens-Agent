"""Run the vNext 1.1 Provider model-quality gates with explicit cost controls.

Zero-call by default. Live model execution requires both
``--execute-provider-gate`` and ``--confirm-live-cost``. Development defaults to
an inexpensive representative canary; the 60 Intent + 44 Tool Selection release
cohort additionally requires ``--full-release-gate``.

Cost safety has three independent layers:

1. a deterministic Canary selects a small category-diverse cohort;
2. ``max_provider_calls`` is enforced inside the HTTP adapter, so retries also
   consume the same hard budget;
3. an exact run fingerprint reuses a measured local snapshot instead of paying
   for the identical provider/model/prompt/schema/dataset/configuration twice.

The JSON snapshot under ``data/local/`` contains no credentials, prompts, user
messages or model output.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
from typing import TypeVar

from app.core.config import Settings, get_settings
from app.evals.career_intent import (
    IntentEvalCase,
    career_intent_eval_dataset_path,
    load_career_intent_eval_dataset,
)
from app.evals.career_provider_gates import (
    IntentProviderReport,
    ProviderGateStatus,
    ToolSelectionProviderReport,
    measure_career_intent_provider_quality,
    measure_career_tool_selection_provider_quality,
    render_intent_provider_report,
    render_tool_selection_provider_report,
)
from app.evals.career_tool_selection import (
    ToolSelectionEvalCase,
    load_career_tool_selection_eval_dataset,
    tool_selection_eval_dataset_path,
)
from app.evals.provider_smoke import DEFAULT_PROVIDER_SMOKE_SNAPSHOT
from app.llm.career_intent_models import (
    CAREER_INTENT_PROMPT_VERSION,
    CAREER_INTENT_SCHEMA_VERSION,
    DisabledCareerIntentModel,
    build_career_intent_model,
)

DEFAULT_SNAPSHOT_PATH = (
    DEFAULT_PROVIDER_SMOKE_SNAPSHOT.parent / "career-provider-gates.json"
)
DEFAULT_REPLAY_CACHE_DIR = (
    DEFAULT_PROVIDER_SMOKE_SNAPSHOT.parent / "career-provider-gate-cache"
)
DEFAULT_ESTIMATED_COST_PER_CALL_CNY = 0.08
DEFAULT_CANARY_CASES_PER_GATE = 5

_CaseT = TypeVar("_CaseT", IntentEvalCase, ToolSelectionEvalCase)


@dataclass(frozen=True, slots=True)
class CareerProviderGatePlan:
    mode: str
    intent_cases: tuple[IntentEvalCase, ...]
    tool_selection_cases: tuple[ToolSelectionEvalCase, ...]
    planned_provider_calls: int
    max_provider_calls: int
    estimated_cost_per_call_cny: float
    estimated_max_cost_cny: float
    run_fingerprint: str


@dataclass(frozen=True, slots=True)
class CareerProviderGateResult:
    checked_at: str
    provider: str
    model: str
    execution_requested: bool
    live_cost_confirmed: bool
    mode: str
    planned_provider_calls: int
    max_provider_calls: int
    provider_calls: int
    rate_limited: int
    provider_input_tokens: int
    provider_output_tokens: int
    provider_total_tokens: int
    estimated_cost_per_call_cny: float
    estimated_spend_cny: float
    estimated_max_cost_cny: float
    run_fingerprint: str
    replay_cache_hit: bool
    prompt_version: str
    schema_version: str
    intent: IntentProviderReport
    tool_selection: ToolSelectionProviderReport


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute-provider-gate",
        action="store_true",
        help="Allow real Provider calls. Requires --confirm-live-cost.",
    )
    parser.add_argument(
        "--confirm-live-cost",
        action="store_true",
        help="Acknowledge the planned billed-call budget.",
    )
    parser.add_argument(
        "--full-release-gate",
        action="store_true",
        help="Run all 60 Intent + 44 Tool Selection cases instead of a canary.",
    )
    parser.add_argument(
        "--canary-cases-per-gate",
        type=int,
        default=DEFAULT_CANARY_CASES_PER_GATE,
        help="Representative cases selected per gate in canary mode (default: 5).",
    )
    parser.add_argument(
        "--max-provider-calls",
        type=int,
        default=None,
        help=(
            "Hard cap on actual HTTP attempts, including retries. Defaults to the "
            "planned case count, which prevents retry amplification."
        ),
    )
    parser.add_argument(
        "--estimated-cost-per-call-cny",
        type=float,
        default=DEFAULT_ESTIMATED_COST_PER_CALL_CNY,
        help="Local cost estimate used only for budgeting/reporting (default: 0.08).",
    )
    parser.add_argument(
        "--max-cost-cny",
        type=float,
        default=None,
        help="Refuse live execution if the hard call budget could exceed this amount.",
    )
    parser.add_argument(
        "--refresh-replay-cache",
        action="store_true",
        help="Ignore an exact measured snapshot and pay for a fresh run.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the machine-readable snapshot instead of a summary.",
    )
    parser.add_argument(
        "--pace-seconds",
        type=float,
        default=0.0,
        help="Minimum seconds between Provider calls. 0 disables pacing.",
    )
    return parser.parse_args()


def build_provider_gate_plan(
    *,
    settings: Settings,
    full_release_gate: bool = False,
    canary_cases_per_gate: int = DEFAULT_CANARY_CASES_PER_GATE,
    max_provider_calls: int | None = None,
    estimated_cost_per_call_cny: float = DEFAULT_ESTIMATED_COST_PER_CALL_CNY,
    max_cost_cny: float | None = None,
) -> CareerProviderGatePlan:
    if canary_cases_per_gate < 1:
        raise ValueError("canary_cases_per_gate must be >= 1")
    if estimated_cost_per_call_cny < 0:
        raise ValueError("estimated_cost_per_call_cny must be >= 0")
    if max_provider_calls is not None and max_provider_calls < 1:
        raise ValueError("max_provider_calls must be >= 1")
    if max_cost_cny is not None and max_cost_cny < 0:
        raise ValueError("max_cost_cny must be >= 0")

    all_intent = load_career_intent_eval_dataset()
    all_tool = load_career_tool_selection_eval_dataset()
    if full_release_gate:
        mode = "release"
        intent_cases = all_intent
        tool_cases = all_tool
    else:
        mode = "canary"
        intent_cases = _representative_cases(all_intent, canary_cases_per_gate)
        tool_cases = _representative_cases(all_tool, canary_cases_per_gate)

    planned_calls = len(intent_cases) + len(tool_cases)
    hard_call_budget = max_provider_calls or planned_calls
    if hard_call_budget < planned_calls:
        raise ValueError(
            "max_provider_calls cannot cover the selected cases; reduce the canary "
            f"size or allow at least {planned_calls} call(s)"
        )
    estimated_max_cost = hard_call_budget * estimated_cost_per_call_cny
    if max_cost_cny is not None and estimated_max_cost > max_cost_cny + 1e-9:
        affordable_calls = (
            math.floor(max_cost_cny / estimated_cost_per_call_cny)
            if estimated_cost_per_call_cny > 0
            else hard_call_budget
        )
        raise ValueError(
            "provider cost budget is too small for the requested hard call cap: "
            f"maxCostCny={max_cost_cny:.2f} allows about {affordable_calls} call(s), "
            f"but maxProviderCalls={hard_call_budget}"
        )

    run_fingerprint = _run_fingerprint(
        settings=settings,
        mode=mode,
        intent_case_ids=tuple(case.case_id for case in intent_cases),
        tool_case_ids=tuple(case.case_id for case in tool_cases),
    )
    return CareerProviderGatePlan(
        mode=mode,
        intent_cases=intent_cases,
        tool_selection_cases=tool_cases,
        planned_provider_calls=planned_calls,
        max_provider_calls=hard_call_budget,
        estimated_cost_per_call_cny=estimated_cost_per_call_cny,
        estimated_max_cost_cny=estimated_max_cost,
        run_fingerprint=run_fingerprint,
    )


def _representative_cases(cases: tuple[_CaseT, ...], limit: int) -> tuple[_CaseT, ...]:
    """Select a deterministic category-diverse canary before filling in file order."""

    if limit >= len(cases):
        return cases
    selected: list[_CaseT] = []
    seen_categories: set[str] = set()
    for case in cases:
        category = str(case.category)
        if category in seen_categories:
            continue
        selected.append(case)
        seen_categories.add(category)
        if len(selected) == limit:
            return tuple(selected)
    selected_ids = {case.case_id for case in selected}
    for case in cases:
        if case.case_id in selected_ids:
            continue
        selected.append(case)
        if len(selected) == limit:
            break
    return tuple(selected)


def _run_fingerprint(
    *,
    settings: Settings,
    mode: str,
    intent_case_ids: tuple[str, ...],
    tool_case_ids: tuple[str, ...],
) -> str:
    payload = {
        "provider": settings.career_intent_provider.strip().casefold(),
        "model": settings.career_intent_model.strip(),
        "baseUrl": settings.openai_base_url.rstrip("/"),
        "apiStyle": settings.career_intent_api_style,
        "enableThinking": settings.career_intent_enable_thinking,
        "maxCompletionTokens": settings.career_intent_max_completion_tokens,
        "promptVersion": CAREER_INTENT_PROMPT_VERSION,
        "schemaVersion": CAREER_INTENT_SCHEMA_VERSION,
        "intentDataset": _file_sha256(career_intent_eval_dataset_path()),
        "toolDataset": _file_sha256(tool_selection_eval_dataset_path()),
        "mode": mode,
        "intentCaseIds": intent_case_ids,
        "toolCaseIds": tool_case_ids,
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_career_provider_gates(
    *,
    settings: Settings,
    execute_provider_gate: bool,
    confirm_live_cost: bool,
    pace_seconds: float = 0.0,
    plan: CareerProviderGatePlan | None = None,
) -> CareerProviderGateResult:
    active_plan = plan or build_provider_gate_plan(settings=settings)
    requested = execute_provider_gate and confirm_live_cost
    active_settings = (
        settings.model_copy(
            update={"career_intent_min_request_interval_seconds": pace_seconds}
        )
        if pace_seconds > 0
        else settings
    )
    model = (
        build_career_intent_model(
            active_settings,
            max_provider_attempts=active_plan.max_provider_calls,
        )
        if requested
        else DisabledCareerIntentModel()
    )

    intent_report = measure_career_intent_provider_quality(
        model=model,
        cases=active_plan.intent_cases,
    )
    tool_report = measure_career_tool_selection_provider_quality(
        model=model,
        cases=active_plan.tool_selection_cases,
    )
    provider_calls = getattr(model, "attempts", 0)
    return CareerProviderGateResult(
        checked_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        provider=active_settings.career_intent_provider.strip() or "disabled",
        model=model.model_name,
        execution_requested=execute_provider_gate,
        live_cost_confirmed=confirm_live_cost,
        mode=active_plan.mode,
        planned_provider_calls=active_plan.planned_provider_calls,
        max_provider_calls=active_plan.max_provider_calls,
        provider_calls=provider_calls,
        rate_limited=getattr(model, "rate_limited", 0),
        provider_input_tokens=getattr(model, "input_tokens", 0),
        provider_output_tokens=getattr(model, "output_tokens", 0),
        provider_total_tokens=getattr(model, "total_tokens", 0),
        estimated_cost_per_call_cny=active_plan.estimated_cost_per_call_cny,
        estimated_spend_cny=provider_calls * active_plan.estimated_cost_per_call_cny,
        estimated_max_cost_cny=active_plan.estimated_max_cost_cny,
        run_fingerprint=active_plan.run_fingerprint,
        replay_cache_hit=False,
        prompt_version=CAREER_INTENT_PROMPT_VERSION,
        schema_version=CAREER_INTENT_SCHEMA_VERSION,
        intent=intent_report,
        tool_selection=tool_report,
    )


def save_career_provider_gate_snapshot(
    result: CareerProviderGateResult,
    *,
    path: Path = DEFAULT_SNAPSHOT_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(_serialize(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def save_replay_snapshot(
    result: CareerProviderGateResult,
    *,
    cache_dir: Path = DEFAULT_REPLAY_CACHE_DIR,
) -> None:
    """Persist only fully measured paid evidence, keyed by exact run identity."""

    statuses = (result.intent.status, result.tool_selection.status)
    if (
        not result.live_cost_confirmed
        or any(
            status not in {ProviderGateStatus.PASS, ProviderGateStatus.FAIL}
            for status in statuses
        )
        or result.intent.transport_failures > 0
        or result.tool_selection.transport_failures > 0
    ):
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{result.run_fingerprint}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(_serialize(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_replay_snapshot(
    *,
    run_fingerprint: str,
    cache_dir: Path = DEFAULT_REPLAY_CACHE_DIR,
    path: Path | None = None,
) -> dict[str, object] | None:
    """Reuse only a fully measured snapshot with the exact same run identity."""

    replay_path = path or cache_dir / f"{run_fingerprint}.json"
    try:
        payload = json.loads(replay_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if payload.get("runFingerprint") != run_fingerprint:
        return None
    intent = payload.get("intent")
    tool = payload.get("toolSelection")
    if not isinstance(intent, dict) or not isinstance(tool, dict):
        return None
    measured = {"pass", "fail"}
    if intent.get("status") not in measured or tool.get("status") not in measured:
        return None
    if intent.get("transportFailures", 0) or tool.get("transportFailures", 0):
        return None
    cached = dict(payload)
    cached["replayCacheHit"] = True
    cached["providerCallsThisRun"] = 0
    return cached


def _serialize(result: CareerProviderGateResult) -> dict[str, object]:
    payload = asdict(result)
    for old, new in (
        ("checked_at", "checkedAt"),
        ("execution_requested", "executionRequested"),
        ("live_cost_confirmed", "liveCostConfirmed"),
        ("planned_provider_calls", "plannedProviderCalls"),
        ("max_provider_calls", "maxProviderCalls"),
        ("provider_calls", "providerCalls"),
        ("rate_limited", "rateLimited"),
        ("provider_input_tokens", "providerInputTokens"),
        ("provider_output_tokens", "providerOutputTokens"),
        ("provider_total_tokens", "providerTotalTokens"),
        ("estimated_cost_per_call_cny", "estimatedCostPerCallCny"),
        ("estimated_spend_cny", "estimatedSpendCny"),
        ("estimated_max_cost_cny", "estimatedMaxCostCny"),
        ("run_fingerprint", "runFingerprint"),
        ("replay_cache_hit", "replayCacheHit"),
        ("prompt_version", "promptVersion"),
        ("schema_version", "schemaVersion"),
    ):
        payload[new] = payload.pop(old)
    payload["providerCallsThisRun"] = payload["providerCalls"]
    payload["toolSelection"] = _camel(payload.pop("tool_selection"))
    payload["intent"] = _camel(payload["intent"])
    return payload


def _camel(value: object) -> object:
    if isinstance(value, dict):
        return {_camel_key(key): _camel(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_camel(item) for item in value]
    return value


def _camel_key(key: str) -> str:
    head, *rest = key.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def career_provider_gate_exit_code(result: CareerProviderGateResult) -> int:
    statuses = (result.intent.status, result.tool_selection.status)
    if any(status is ProviderGateStatus.FAIL for status in statuses):
        return 1
    if any(status is ProviderGateStatus.NOT_MEASURED for status in statuses):
        return 2
    return 0


def _cached_exit_code(payload: dict[str, object]) -> int:
    statuses: list[str] = []
    for key in ("intent", "toolSelection"):
        value = payload.get(key)
        if isinstance(value, dict) and isinstance(value.get("status"), str):
            statuses.append(value["status"])
    if "fail" in statuses:
        return 1
    if any(status not in {"pass", "fail"} for status in statuses) or len(statuses) != 2:
        return 2
    return 0


def _print_plan(plan: CareerProviderGatePlan) -> None:
    print(
        f"mode={plan.mode} plannedCalls={plan.planned_provider_calls} "
        f"maxProviderCalls={plan.max_provider_calls} "
        f"estimatedCost=¥{plan.planned_provider_calls * plan.estimated_cost_per_call_cny:.2f} "
        f"estimatedMaxCost=¥{plan.estimated_max_cost_cny:.2f}"
    )
    print(f"runFingerprint=sha256:{plan.run_fingerprint[:16]}")


def main() -> int:
    args = _arguments()
    settings = get_settings()
    try:
        plan = build_provider_gate_plan(
            settings=settings,
            full_release_gate=args.full_release_gate,
            canary_cases_per_gate=args.canary_cases_per_gate,
            max_provider_calls=args.max_provider_calls,
            estimated_cost_per_call_cny=args.estimated_cost_per_call_cny,
            max_cost_cny=args.max_cost_cny,
        )
    except ValueError as error:
        print(f"refusing provider run: {error}")
        return 2

    requested = args.execute_provider_gate and args.confirm_live_cost
    if requested and not args.refresh_replay_cache:
        cached = load_replay_snapshot(run_fingerprint=plan.run_fingerprint)
        if cached is not None:
            if args.json:
                print(json.dumps(cached, ensure_ascii=False, indent=2))
            else:
                print("Provider Gate: REPLAY CACHE HIT — 0 billed calls this run")
                _print_plan(plan)
                print(
                    "Use --refresh-replay-cache only when you intentionally want a "
                    "fresh paid measurement."
                )
            return _cached_exit_code(cached)

    result = run_career_provider_gates(
        settings=settings,
        execute_provider_gate=args.execute_provider_gate,
        confirm_live_cost=args.confirm_live_cost,
        pace_seconds=args.pace_seconds,
        plan=plan,
    )
    save_career_provider_gate_snapshot(result)
    save_replay_snapshot(result)

    if args.json:
        print(json.dumps(_serialize(result), ensure_ascii=False, indent=2))
    else:
        _print_plan(plan)
        print(render_intent_provider_report(result.intent))
        print()
        print(render_tool_selection_provider_report(result.tool_selection))
        print()
        print(
            f"provider={result.provider} model={result.model} "
            f"providerCalls={result.provider_calls} "
            f"tokens={result.provider_input_tokens}+{result.provider_output_tokens}="
            f"{result.provider_total_tokens} "
            f"estimatedSpend=¥{result.estimated_spend_cny:.2f} "
            f"prompt={result.prompt_version} schema={result.schema_version}"
        )
        if not requested:
            print(
                "note: no Provider was contacted. Live execution requires both "
                "--execute-provider-gate and --confirm-live-cost."
            )
        if result.mode == "canary":
            print(
                "note: canary results are development evidence only; they never "
                "replace the 60+44 full release gate."
            )

    return career_provider_gate_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
