"""Run the vNext 1.1 Provider model-quality gates for Intent and Tool Selection.

Zero-call by default.  Live model execution requires both
`--execute-provider-gate` and `--confirm-live-cost`, matching the convention used
by the other provider checks in this directory.

A full run spends one call per case: 60 for the Intent cohort and 44 for the Tool
Selection cohort.  Exit codes separate "not measured" from "measured and failed",
because a gate that has not run must never be read as a gate that passed:

    0  every gate that ran passed
    1  at least one gate ran and failed
    2  at least one gate could not be measured (provider disabled or refused)

The JSON snapshot written to `data/local/` contains only counts, versions and
case identifiers.  It never contains prompts, user messages or model output.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path

from app.core.config import Settings, get_settings
from app.evals.career_intent import load_career_intent_eval_dataset
from app.evals.career_provider_gates import (
    IntentProviderReport,
    ProviderGateStatus,
    ToolSelectionProviderReport,
    measure_career_intent_provider_quality,
    measure_career_tool_selection_provider_quality,
    render_intent_provider_report,
    render_tool_selection_provider_report,
)
from app.llm.career_intent_models import (
    CAREER_INTENT_PROMPT_VERSION,
    CAREER_INTENT_SCHEMA_VERSION,
    DisabledCareerIntentModel,
    build_career_intent_model,
)
from app.evals.provider_smoke import DEFAULT_PROVIDER_SMOKE_SNAPSHOT

#: Derived from the existing smoke snapshot location so this script cannot drift
#: into a directory the repository does not ignore.  A hand-computed path here
#: would place a local artifact inside a tracked directory.
DEFAULT_SNAPSHOT_PATH = (
    DEFAULT_PROVIDER_SMOKE_SNAPSHOT.parent / "career-provider-gates.json"
)


@dataclass(frozen=True, slots=True)
class CareerProviderGateResult:
    checked_at: str
    provider: str
    model: str
    execution_requested: bool
    live_cost_confirmed: bool
    provider_calls: int
    rate_limited: int
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
        help="Acknowledge that a full run spends one Provider call per case.",
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
        help=(
            "Minimum seconds between Provider calls. The configured endpoint "
            "enforces a request window, so pacing a long cohort is cheaper than "
            "retrying 429s. 0 disables pacing."
        ),
    )
    return parser.parse_args()


def run_career_provider_gates(
    *,
    settings: Settings,
    execute_provider_gate: bool,
    confirm_live_cost: bool,
    pace_seconds: float = 0.0,
) -> CareerProviderGateResult:
    requested = execute_provider_gate and confirm_live_cost
    active_settings = (
        settings.model_copy(
            update={"career_intent_min_request_interval_seconds": pace_seconds}
        )
        if pace_seconds > 0
        else settings
    )
    model = (
        build_career_intent_model(active_settings)
        if requested
        else DisabledCareerIntentModel()
    )

    if not requested and not isinstance(model, DisabledCareerIntentModel):
        raise RuntimeError("refusing to contact a Provider without cost confirmation")

    intent_report = measure_career_intent_provider_quality(
        model=model,
        cases=load_career_intent_eval_dataset(),
    )
    tool_report = measure_career_tool_selection_provider_quality(model=model)

    return CareerProviderGateResult(
        checked_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        provider=active_settings.career_intent_provider.strip() or "disabled",
        model=model.model_name,
        execution_requested=execute_provider_gate,
        live_cost_confirmed=confirm_live_cost,
        provider_calls=getattr(model, "attempts", 0),
        rate_limited=getattr(model, "rate_limited", 0),
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
    """Persist a non-secret summary in gitignored local data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(_serialize(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _serialize(result: CareerProviderGateResult) -> dict[str, object]:
    payload = asdict(result)
    payload["checkedAt"] = payload.pop("checked_at")
    payload["executionRequested"] = payload.pop("execution_requested")
    payload["liveCostConfirmed"] = payload.pop("live_cost_confirmed")
    payload["providerCalls"] = payload.pop("provider_calls")
    payload["rateLimited"] = payload.pop("rate_limited")
    payload["promptVersion"] = payload.pop("prompt_version")
    payload["schemaVersion"] = payload.pop("schema_version")
    payload["toolSelection"] = _camel(payload.pop("tool_selection"))
    payload["intent"] = _camel(payload["intent"])
    return payload


def _camel(value: object) -> object:
    """Convert dataclass snapshots to the camelCase used by existing checks."""

    if isinstance(value, dict):
        return {
            _camel_key(key): _camel(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_camel(item) for item in value]
    return value


def _camel_key(key: str) -> str:
    head, *rest = key.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def career_provider_gate_exit_code(result: CareerProviderGateResult) -> int:
    """Map gate statuses onto process exit codes.

    "Could not be measured" is deliberately distinct from "measured and failed",
    so a caller can tell a broken gate from an unfunded Provider.
    """

    statuses = (result.intent.status, result.tool_selection.status)
    if any(status is ProviderGateStatus.FAIL for status in statuses):
        return 1
    if any(status is ProviderGateStatus.NOT_MEASURED for status in statuses):
        return 2
    return 0


def main() -> int:
    args = _arguments()
    result = run_career_provider_gates(
        settings=get_settings(),
        execute_provider_gate=args.execute_provider_gate,
        confirm_live_cost=args.confirm_live_cost,
        pace_seconds=args.pace_seconds,
    )
    save_career_provider_gate_snapshot(result)

    if args.json:
        print(json.dumps(_serialize(result), ensure_ascii=False, indent=2))
    else:
        print(render_intent_provider_report(result.intent))
        print()
        print(render_tool_selection_provider_report(result.tool_selection))
        print()
        print(
            f"provider={result.provider} model={result.model} "
            f"providerCalls={result.provider_calls} "
            f"prompt={result.prompt_version} schema={result.schema_version}"
        )
        if not result.execution_requested:
            print(
                "note: no Provider was contacted. Re-run with "
                "--execute-provider-gate --confirm-live-cost to measure."
            )

    return career_provider_gate_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())