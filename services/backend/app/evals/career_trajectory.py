"""Deterministic vNext 1.1 governed-loop Trajectory / Trace Replay Gate.

This module owns the Eval boundary only.  It drives Agent A's frozen
``CareerAgentGovernedLoopRuntime`` and never implements a retry loop, a planner,
or a second runtime of its own.

**Why this gate reports incomplete PRD coverage.**

PRD 15.3 lists ten multi-turn trajectory shapes and requires at least 30 cases.
Empirical probing of the frozen runtime shows it is a *single-pass, ordered,
bounded* executor: it iterates the selected tools exactly once and has no retry,
replan, interrupt/resume, stale detection, or cost-gated tool.  Seven of the ten
shapes therefore cannot be produced end to end, and three of them can only be
produced in part.  This gate states that explicitly through a machine-checked
coverage ledger instead of manufacturing cases that would fake coverage.

Details of each blocked shape, with the observed terminal status used as
evidence, are in ``data/evals/career-trajectory/README.md``.

What this gate does prove, with zero Provider calls and zero business writes:

- exact terminal status and **ordered trace events** for every reachable path;
- trace vocabulary is closed, so no chain-of-thought or raw business text can leak;
- every trace fingerprint is a sha256 digest, never raw message/JD/Resume content;
- **trace replay determinism** -- the same frozen input yields identical trace fingerprints;
- business code is reached exactly when the trajectory says it should be.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from app.agent.context import CareerAgentContext, CareerAgentJobContext
from app.agent.execution_gate import CareerAgentGovernedToolExecutor
from app.agent.governed_loop_runtime import (
    CareerAgentGovernedLoopRuntime,
    CareerAgentPlannedToolRequest,
)
from app.agent.intent import CareerIntentResolutionContext, CareerIntentRouter
from app.agent.tool_loop import CareerAgentLoopBudget
from app.agent.tool_registry import (
    CareerAgentToolError,
    CareerAgentToolName,
    CareerAgentToolRegistry,
    JobPreparationRequest,
    RankMatchReportsRequest,
    TargetCohortGapsRequest,
)
from app.agent.tool_selection import CareerAgentToolSelector

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

_TRACE_VOCABULARY = frozenset(
    {
        "intent_routed",
        "clarification",
        "unsupported",
        "blocked",
        "tool_selected",
        "tool_called",
        "pending_action",
        "tool_result",
        "failed",
        "finished",
    }
)

_TOOL_REQUEST_REQUEST_TYPE: dict[str, type[object]] = {
    "rank_match_reports": RankMatchReportsRequest,
    "target_cohort_gaps": TargetCohortGapsRequest,
    "job_preparation": JobPreparationRequest,
}

_TOOL_REQUIRED_EVENTS = ("tool_selected", "tool_called", "pending_action", "tool_result")
_TOOL_OPTIONAL_EVENTS = ("failed",)


class CareerTrajectoryShape(StrEnum):
    """The ten multi-turn shapes enumerated by PRD 15.3."""

    RANKING_FINISH = "ranking_finish"
    RANKING_HITL_GAP = "ranking_hitl_gap"
    RANKING_GAP_PREPARATION = "ranking_gap_preparation"
    TOOL_EMPTY_CLARIFICATION = "tool_empty_clarification"
    INVALID_PARAMS_CORRECTED_RETRY = "invalid_params_corrected_retry"
    TRANSIENT_ERROR_BOUNDED_RETRY = "transient_error_bounded_retry"
    UNKNOWN_TOOL_REPLAN = "unknown_tool_replan"
    SAME_TOOL_LOOP_STOPPED = "same_tool_loop_stopped"
    STALE_TERMINATE = "stale_terminate"
    COST_ACTION_PENDING_ACTION = "cost_action_pending_action"


class CareerTrajectoryShapeStatus(StrEnum):
    COVERED = "covered"
    PARTIAL = "partial"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CareerTrajectoryShapeCoverage:
    """Machine-checked verdict on one PRD 15.3 shape."""

    shape: CareerTrajectoryShape
    status: CareerTrajectoryShapeStatus
    evidence: str
    reason: str | None = None
    gap_id: str | None = None


_SHAPE_COVERAGE: tuple[CareerTrajectoryShapeCoverage, ...] = (
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.RANKING_FINISH,
        status=CareerTrajectoryShapeStatus.COVERED,
        evidence="probe: status=completed, trace=intent_routed > tool_selected > tool_called > tool_result > finished",
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.RANKING_HITL_GAP,
        status=CareerTrajectoryShapeStatus.PARTIAL,
        evidence="probe: status=completed for rank+gaps; no interrupt/resume event exists in the 1.1 loop",
        reason=(
            "The two-tool ordering Ranking -> Gap is covered, but the HITL interrupt "
            "between them is not representable: CareerAgentGovernedLoopStatus has no "
            "interrupt state and the runtime has no resume path. HITL lives in the "
            "vNext 1.0 LangGraph durable runtime."
        ),
        gap_id="GAP-6",
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.RANKING_GAP_PREPARATION,
        status=CareerTrajectoryShapeStatus.COVERED,
        evidence="probe: status=completed, three ordered tool cycles then finished",
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.TOOL_EMPTY_CLARIFICATION,
        status=CareerTrajectoryShapeStatus.BLOCKED,
        evidence="probe: empty goals -> status=completed, trace=intent_routed > finished, no clarification event",
        reason=(
            "An intent that selects no tool completes silently instead of asking for "
            "clarification. clarification_required is only reachable when the intent "
            "already carries needs_clarification, so 'tool empty implies clarification' "
            "is not implemented."
        ),
        gap_id="GAP-5",
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.INVALID_PARAMS_CORRECTED_RETRY,
        status=CareerTrajectoryShapeStatus.PARTIAL,
        evidence="probe: malformed args -> status=failed, error_code=invalid_tool_params (structured, non-retryable)",
        reason=(
            "Invalid parameters fail closed structurally, but no in-runtime corrected "
            "retry exists. A retry would have to be caller-driven across separate runs."
        ),
        gap_id="GAP-7",
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.TRANSIENT_ERROR_BOUNDED_RETRY,
        status=CareerTrajectoryShapeStatus.BLOCKED,
        evidence="the runtime has no transient-error branch and never re-invokes a tool",
        reason=(
            "CareerAgentGovernedLoopRuntime.run iterates the selection list exactly once; "
            "there is no retry loop and no transient-error classification, so bounded "
            "retry cannot be observed."
        ),
        gap_id="GAP-7",
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.UNKNOWN_TOOL_REPLAN,
        status=CareerTrajectoryShapeStatus.BLOCKED,
        evidence="probe: unregistered goal -> status=failed, error_code=invalid_tool_params (never unknown_tool)",
        reason=(
            "An unknown tool surfaces as invalid_tool_params because selection failure is "
            "caught as a plan error. CareerAgentLoopErrorCode.UNKNOWN_TOOL is unreachable "
            "on this path, and there is no replan step."
        ),
        gap_id="GAP-8",
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.SAME_TOOL_LOOP_STOPPED,
        status=CareerTrajectoryShapeStatus.COVERED,
        evidence="probe: duplicated goal -> status=failed, error_code=loop_detected, one workflow call only",
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.STALE_TERMINATE,
        status=CareerTrajectoryShapeStatus.BLOCKED,
        evidence="no stale status, stale error code, or stale check exists in the 1.1 loop",
        reason=(
            "Staleness is detected in the vNext 1.0 LangGraph durable runtime, not in the "
            "vNext 1.1 governed loop. Core must decide where staleness is detected before "
            "this shape can be evaluated here."
        ),
        gap_id="GAP-3",
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.COST_ACTION_PENDING_ACTION,
        status=CareerTrajectoryShapeStatus.BLOCKED,
        evidence="probe: all registered tools report side_effect=read_only, cost=none, gate=none",
        reason=(
            "No registered tool can require cost or human approval, so the pending_action "
            "branch is unreachable from a user message even though "
            "CareerAgentExecutionGate implements it."
        ),
        gap_id="GAP-1",
    ),
)


def career_trajectory_shape_coverage() -> tuple[CareerTrajectoryShapeCoverage, ...]:
    return _SHAPE_COVERAGE


_RELEASE_MINIMUMS: dict[str, int] = {
    "completed_single": 3,
    "completed_multi": 3,
    "completed_triple": 2,
    "clarification": 2,
    "unsupported": 2,
    "blocked": 2,
    "invalid_intent_output": 2,
    "invalid_tool_params": 4,
    "loop_detected": 2,
    "budget_exhausted": 2,
}
_RELEASE_MINIMUM_TOTAL = sum(_RELEASE_MINIMUMS.values())

_BUDGET_FIELDS = frozenset(field.name for field in fields(CareerAgentLoopBudget))

_DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "evals"
    / "career-trajectory"
    / "career-trajectory-v1.jsonl"
)


@dataclass(frozen=True, slots=True)
class CareerTrajectoryEvalContext:
    usable: bool = True
    current_job_id: str | None = None
    run_job_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CareerTrajectoryEvalPlan:
    """One caller-supplied planned tool request."""

    tool: str
    fact_fingerprint: str
    normalized_params: tuple[tuple[str, str], ...]
    request_payload: Mapping[str, object]
    expected_provider_calls: int = 0
    business_writes: int = 0
    external_effects: tuple[str, ...] = ()
    expires_at: str | None = None


@dataclass(frozen=True, slots=True)
class CareerTrajectoryEvalExpected:
    status: str
    error_code: str | None
    trace: tuple[str, ...]
    tool_results: int
    workflow_invocations: int


@dataclass(frozen=True, slots=True)
class CareerTrajectoryEvalCase:
    case_id: str
    family: str
    message: str
    shapes: tuple[CareerTrajectoryShape, ...]
    context: CareerTrajectoryEvalContext
    intent_payload: Mapping[str, object]
    planned_requests: tuple[CareerTrajectoryEvalPlan, ...]
    budget_overrides: Mapping[str, int]
    expected: CareerTrajectoryEvalExpected


@dataclass(frozen=True, slots=True)
class CareerTrajectoryEvalExecution:
    status: str | None
    error_code: str | None
    trace: tuple[str, ...]
    trace_fingerprints: tuple[str, ...]
    tool_results: int
    workflow_invocations: int
    pending_action_present: bool
    replay_stable: bool
    unclassified_error: str | None = None
    trace_leak: str | None = None
    provider_attempts: int = 0
    provider_completed: int = 0
    business_writes: int = 0


@dataclass(frozen=True, slots=True)
class CareerTrajectoryEvalCaseResult:
    case_id: str
    passed: bool
    failure_reasons: tuple[str, ...]
    execution: CareerTrajectoryEvalExecution


@dataclass(frozen=True, slots=True)
class CareerTrajectoryEvalReport:
    total_cases: int
    passed_cases: int
    failed_cases: int
    gate_passed: bool
    unclassified_errors: int
    trace_leaks: int
    unstable_traces: int
    provider_attempts: int
    provider_completed: int
    business_writes: int
    coverage: tuple[CareerTrajectoryShapeCoverage, ...]
    covered_shapes: int
    partial_shapes: int
    blocked_shapes: int
    prd_153_shape_coverage_complete: bool
    prd_153_case_minimum_met: bool
    case_results: tuple[CareerTrajectoryEvalCaseResult, ...]


class _ReplayIntentModel:
    """Deterministic frozen oracle for the Core ``CareerIntentModel`` seam."""

    def __init__(self, payloads: Mapping[str, Mapping[str, object]]) -> None:
        self._payloads = {key: dict(value) for key, value in payloads.items()}

    def route(self, user_message: str) -> dict[str, object]:
        return dict(self._payloads[user_message])


class _CountingRanking:
    def __init__(self) -> None:
        self.calls = 0

    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        include_blocked: bool = False,
        top_n: int | None = None,
    ) -> object:
        self.calls += 1
        return {"jobIds": list(job_ids)}


class _CountingGaps:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, command: object) -> object:
        self.calls += 1
        return {"cohortId": getattr(command, "cohort_id", None)}


class _CountingPreparation:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, job_id: str) -> object:
        self.calls += 1
        return {"jobId": job_id}


class CareerTrajectoryEvalDriver:
    """Drive the real governed loop runtime over frozen trajectory cases.

    The driver only builds a record-only fixture, replays one frozen case, counts
    the workflow invocations the runtime actually caused, and re-runs the case to
    check trace replay determinism.  It contains no runtime, planner, or retry
    logic.
    """

    def run(self, *, case: CareerTrajectoryEvalCase) -> CareerTrajectoryEvalExecution:
        try:
            first = self._drive(case)
        except Exception as exc:
            return CareerTrajectoryEvalExecution(
                status=None,
                error_code=None,
                trace=(),
                trace_fingerprints=(),
                tool_results=0,
                workflow_invocations=0,
                pending_action_present=False,
                replay_stable=False,
                unclassified_error=f"{type(exc).__name__}: {exc}",
            )

        try:
            second = self._drive(case)
            replay_stable = first.trace_fingerprints == second.trace_fingerprints
        except Exception:
            replay_stable = False

        return replace(first, replay_stable=replay_stable)

    def _drive(self, case: CareerTrajectoryEvalCase) -> CareerTrajectoryEvalExecution:
        ranking, gaps, preparation = _CountingRanking(), _CountingGaps(), _CountingPreparation()
        registry = CareerAgentToolRegistry(
            ranking=ranking,
            target_cohort_gaps=gaps,
            job_preparation=preparation,
        )
        runtime = CareerAgentGovernedLoopRuntime(
            router=CareerIntentRouter(model=_ReplayIntentModel({case.message: case.intent_payload})),
            selector=CareerAgentToolSelector(registry=registry),
            executor=CareerAgentGovernedToolExecutor(registry=registry),
            budget=replace(CareerAgentLoopBudget(), **dict(case.budget_overrides)),
        )

        result = runtime.run(
            user_message=case.message,
            context=_build_context(case.context),
            resolution_context=CareerIntentResolutionContext(
                current_job_id=case.context.current_job_id,
                run_job_ids=case.context.run_job_ids,
            ),
            planned_requests=tuple(
                _build_plan(plan) for plan in case.planned_requests
            ),
        )

        leak = _detect_trace_leak(result.trace)
        return CareerTrajectoryEvalExecution(
            status=result.status.value,
            error_code=result.error_code,
            trace=_render_trace(result.trace),
            trace_fingerprints=tuple(event.trace_fingerprint for event in result.trace),
            tool_results=len(result.tool_results),
            workflow_invocations=ranking.calls + gaps.calls + preparation.calls,
            pending_action_present=result.pending_action is not None,
            replay_stable=True,
            trace_leak=leak,
        )


def _render_trace(trace: object) -> tuple[str, ...]:
    return tuple(
        f"{event.event}:{event.tool.value}" if event.tool else event.event
        for event in trace  # type: ignore[union-attr]
    )


def _detect_trace_leak(trace: object) -> str | None:
    """Prove the trace carries digests, not raw business content."""

    for event in trace:  # type: ignore[union-attr]
        if event.event not in _TRACE_VOCABULARY:
            return f"trace carries an unknown event name {event.event!r}"
        for field_name in ("input_fingerprint", "result_fingerprint", "trace_fingerprint"):
            value = getattr(event, field_name)
            if value is None:
                continue
            if not _SHA256_HEX.match(value):
                return (
                    f"trace field {field_name} on event {event.event!r} is not a sha256 "
                    "digest, so raw business content may have leaked"
                )
    return None


def _build_context(context: CareerTrajectoryEvalContext) -> CareerAgentContext:
    current_job = (
        CareerAgentJobContext(
            id=context.current_job_id,
            title="Eval governed current job",
            company="Eval fixture",
            area=None,
        )
        if context.current_job_id is not None
        else None
    )
    return CareerAgentContext(
        usable=context.usable,
        confirmation_boundary="confirmed_profile_v1",
        profile=None,
        search_intent=None,
        current_job=current_job,
        relevant_evidence=(),
        blockers=(),
        blocker_messages=(),
    )


def _build_plan(plan: CareerTrajectoryEvalPlan) -> CareerAgentPlannedToolRequest:
    return CareerAgentPlannedToolRequest(
        tool=CareerAgentToolName(plan.tool),
        request=_build_request(plan.request_payload, tool=plan.tool),
        normalized_params=plan.normalized_params,
        fact_fingerprint=plan.fact_fingerprint,
        expected_provider_calls=plan.expected_provider_calls,
        business_writes=plan.business_writes,
        external_effects=plan.external_effects,
        expires_at=plan.expires_at,
    )


def _build_request(
    payload: Mapping[str, object],
    *,
    tool: str,
) -> object:
    kind = payload.get("kind")
    if kind == "rank_match_reports":
        return RankMatchReportsRequest(
            job_ids=tuple(_string_list(payload.get("jobIds", []))),
            include_blocked=bool(payload.get("includeBlocked", False)),
            top_n=payload.get("topN"),  # type: ignore[arg-type]
        )
    if kind == "target_cohort_gaps":
        return TargetCohortGapsRequest(
            cohort_id=str(payload.get("cohortId", "")),
            name=str(payload.get("name", "")),
            selected_feedback_ids=tuple(_string_list(payload.get("selectedFeedbackIds", []))),
            selected_job_ids=tuple(_string_list(payload.get("selectedJobIds", []))),
        )
    if kind == "job_preparation":
        job_id = payload.get("jobId")
        return JobPreparationRequest(job_id=job_id if isinstance(job_id, str) else None)
    raise CareerAgentToolError(
        f"trajectory plan for {tool} has an invalid request kind: {kind!r}"
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return list(value)


def load_career_trajectory_eval_dataset(
    path: str | Path = _DEFAULT_DATASET_PATH,
) -> tuple[CareerTrajectoryEvalCase, ...]:
    dataset_path = Path(path)
    cases: list[CareerTrajectoryEvalCase] = []
    case_ids: set[str] = set()
    for line_number, raw_line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid Trajectory Eval JSONL at line {line_number}"
            ) from exc
        case = _parse_case(payload, line_number=line_number)
        if case.case_id in case_ids:
            raise ValueError(f"duplicate Trajectory Eval case id: {case.case_id}")
        case_ids.add(case.case_id)
        cases.append(case)

    messages = Counter(case.message for case in cases)
    duplicated = [message for message, count in messages.items() if count > 1]
    if duplicated:
        raise ValueError(
            "Trajectory Eval messages must be unique because the replay oracle is keyed "
            "by message: " + ", ".join(sorted(duplicated))
        )

    validate_career_trajectory_release_dataset(tuple(cases))
    return tuple(cases)


def validate_career_trajectory_release_dataset(
    cases: tuple[CareerTrajectoryEvalCase, ...],
) -> None:
    if len(cases) < _RELEASE_MINIMUM_TOTAL:
        raise ValueError(
            f"Trajectory Eval requires at least {_RELEASE_MINIMUM_TOTAL} cases"
        )
    duplicate_ids = [
        case_id
        for case_id, count in Counter(case.case_id for case in cases).items()
        if count > 1
    ]
    if duplicate_ids:
        raise ValueError(
            "duplicate Trajectory Eval case ids: " + ", ".join(sorted(duplicate_ids))
        )

    family_counts = Counter(case.family for case in cases)
    missing = [
        f"{family} >= {minimum} (got {family_counts[family]})"
        for family, minimum in _RELEASE_MINIMUMS.items()
        if family_counts[family] < minimum
    ]
    if missing:
        raise ValueError(
            "Trajectory Eval dataset family minimums failed: " + "; ".join(missing)
        )


def evaluate_career_trajectories(
    *,
    driver: CareerTrajectoryEvalDriver,
    cases: tuple[CareerTrajectoryEvalCase, ...],
    require_release_dataset: bool = True,
) -> CareerTrajectoryEvalReport:
    if not cases:
        raise ValueError("Trajectory Eval requires at least one case")
    if require_release_dataset:
        validate_career_trajectory_release_dataset(cases)

    results = tuple(_evaluate_case(driver=driver, case=case) for case in cases)
    paired = tuple(zip(cases, results))
    passed_cases = sum(result.passed for result in results)
    unclassified_errors = sum(
        1 for _, result in paired if result.execution.unclassified_error is not None
    )
    trace_leaks = sum(1 for _, result in paired if result.execution.trace_leak is not None)
    unstable_traces = sum(
        1
        for _, result in paired
        if result.execution.unclassified_error is None and not result.execution.replay_stable
    )

    counts = Counter(item.status for item in _SHAPE_COVERAGE)
    return CareerTrajectoryEvalReport(
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=len(results) - passed_cases,
        gate_passed=(
            passed_cases == len(results)
            and unclassified_errors == 0
            and trace_leaks == 0
            and unstable_traces == 0
        ),
        unclassified_errors=unclassified_errors,
        trace_leaks=trace_leaks,
        unstable_traces=unstable_traces,
        provider_attempts=sum(result.execution.provider_attempts for result in results),
        provider_completed=sum(result.execution.provider_completed for result in results),
        business_writes=sum(result.execution.business_writes for result in results),
        coverage=_SHAPE_COVERAGE,
        covered_shapes=counts[CareerTrajectoryShapeStatus.COVERED],
        partial_shapes=counts[CareerTrajectoryShapeStatus.PARTIAL],
        blocked_shapes=counts[CareerTrajectoryShapeStatus.BLOCKED],
        prd_153_shape_coverage_complete=(
            counts[CareerTrajectoryShapeStatus.COVERED] == len(CareerTrajectoryShape)
        ),
        prd_153_case_minimum_met=len(results) >= 30,
        case_results=results,
    )


def _evaluate_case(
    *,
    driver: CareerTrajectoryEvalDriver,
    case: CareerTrajectoryEvalCase,
) -> CareerTrajectoryEvalCaseResult:
    failure_reasons: list[str] = []
    try:
        execution = driver.run(case=case)
    except Exception as exc:
        execution = CareerTrajectoryEvalExecution(
            status=None,
            error_code=None,
            trace=(),
            trace_fingerprints=(),
            tool_results=0,
            workflow_invocations=0,
            pending_action_present=False,
            replay_stable=False,
            unclassified_error=f"driver raised {type(exc).__name__}: {exc}",
        )

    _assert_safety(execution=execution, failures=failure_reasons)
    _assert_matches_expectation(execution=execution, case=case, failures=failure_reasons)

    return CareerTrajectoryEvalCaseResult(
        case_id=case.case_id,
        passed=not failure_reasons,
        failure_reasons=tuple(failure_reasons),
        execution=execution,
    )


def _assert_safety(
    *,
    execution: CareerTrajectoryEvalExecution,
    failures: list[str],
) -> None:
    if execution.unclassified_error is not None:
        failures.append(
            "unclassified error: the runtime must fail through a governed result, "
            f"got {execution.unclassified_error}"
        )
    if execution.trace_leak is not None:
        failures.append(f"trace leak: {execution.trace_leak}")
    if execution.unclassified_error is None and not execution.replay_stable:
        failures.append("trace replay is not deterministic for identical frozen input")
    for field_name, actual in (
        ("provider attempts", execution.provider_attempts),
        ("provider completed", execution.provider_completed),
        ("business writes", execution.business_writes),
    ):
        if actual != 0:
            failures.append(
                f"{field_name} must be 0 during deterministic Trajectory Eval, got {actual}"
            )


def _assert_matches_expectation(
    *,
    execution: CareerTrajectoryEvalExecution,
    case: CareerTrajectoryEvalCase,
    failures: list[str],
) -> None:
    expected = case.expected
    if execution.status != expected.status:
        failures.append(f"status expected {expected.status!r}, got {execution.status!r}")
    if execution.error_code != expected.error_code:
        failures.append(
            f"error_code expected {expected.error_code!r}, got {execution.error_code!r}"
        )
    if execution.trace != expected.trace:
        failures.append(f"trace expected {expected.trace!r}, got {execution.trace!r}")
    if execution.tool_results != expected.tool_results:
        failures.append(
            f"tool results expected {expected.tool_results}, got {execution.tool_results}"
        )
    if execution.workflow_invocations != expected.workflow_invocations:
        failures.append(
            f"workflow invocations expected {expected.workflow_invocations}, "
            f"got {execution.workflow_invocations}"
        )


def _parse_case(payload: object, *, line_number: int) -> CareerTrajectoryEvalCase:
    if not isinstance(payload, dict):
        raise ValueError(f"Trajectory Eval line {line_number} must be an object")

    case_id = _required_string(payload, "id", line_number=line_number)
    family = _required_string(payload, "family", line_number=line_number)
    if family not in _RELEASE_MINIMUMS:
        raise ValueError(
            f"Trajectory Eval line {line_number} has unknown family {family!r}"
        )
    message = _required_string(payload, "message", line_number=line_number)
    shapes = _parse_shapes(payload.get("shapes", []), line_number=line_number)

    context_payload = _object(payload.get("context", {}), field="context", line_number=line_number)
    context = CareerTrajectoryEvalContext(
        usable=_optional_bool(context_payload.get("usable", True), line_number=line_number),
        current_job_id=_optional_string(
            context_payload.get("currentJobId"),
            field="context.currentJobId",
            line_number=line_number,
        ),
        run_job_ids=tuple(
            _string_list_field(
                context_payload.get("runJobIds", []),
                field="context.runJobIds",
                line_number=line_number,
            )
        ),
    )

    intent_payload = _object(payload.get("intent"), field="intent", line_number=line_number)
    plans_payload = payload.get("plannedRequests", [])
    if not isinstance(plans_payload, list):
        raise ValueError(
            f"Trajectory Eval line {line_number} field plannedRequests must be an array"
        )
    plans = tuple(
        _parse_plan(item, line_number=line_number, index=index)
        for index, item in enumerate(plans_payload)
    )
    budget_overrides = _parse_budget(payload.get("budget", {}), line_number=line_number)

    expected_payload = _object(payload.get("expected"), field="expected", line_number=line_number)
    expected = CareerTrajectoryEvalExpected(
        status=_required_string(expected_payload, "status", line_number=line_number),
        error_code=_optional_string(
            expected_payload.get("errorCode"),
            field="expected.errorCode",
            line_number=line_number,
        ),
        trace=tuple(
            _string_list_field(
                expected_payload.get("trace", []),
                field="expected.trace",
                line_number=line_number,
            )
        ),
        tool_results=_required_int(expected_payload, "toolResults", line_number=line_number),
        workflow_invocations=_required_int(
            expected_payload, "workflowInvocations", line_number=line_number
        ),
    )

    case = CareerTrajectoryEvalCase(
        case_id=case_id,
        family=family,
        message=message,
        shapes=shapes,
        context=context,
        intent_payload=intent_payload,
        planned_requests=plans,
        budget_overrides=budget_overrides,
        expected=expected,
    )
    _validate_case_semantics(case)
    return case


def _validate_case_semantics(case: CareerTrajectoryEvalCase) -> None:
    case_id = case.case_id
    expected = case.expected

    for event in expected.trace:
        name = event.split(":", 1)[0]
        if name not in _TRACE_VOCABULARY:
            raise ValueError(f"{case_id}: trace event {event!r} is not in the trace vocabulary")
    for event in expected.trace:
        name, _, tool = event.partition(":")
        if name in _TOOL_REQUIRED_EVENTS and not tool:
            raise ValueError(f"{case_id}: trace event {event!r} must name its tool")
        if name not in _TOOL_REQUIRED_EVENTS and name not in _TOOL_OPTIONAL_EVENTS and tool:
            raise ValueError(f"{case_id}: trace event {event!r} must not name a tool")

    if expected.trace and expected.trace[0] not in ("intent_routed", "failed"):
        raise ValueError(
            f"{case_id}: a trajectory must start with intent_routed, or with failed when "
            "the intent contract rejects the model output"
        )
    if expected.status == "completed" and expected.trace[-1] != "finished":
        raise ValueError(f"{case_id}: a completed trajectory must end with finished")
    if expected.status == "failed":
        if expected.error_code is None:
            raise ValueError(f"{case_id}: a failed trajectory requires an errorCode")
        if not expected.trace or not expected.trace[-1].startswith("failed"):
            raise ValueError(f"{case_id}: a failed trajectory must end with a failed event")
    elif expected.error_code is not None:
        raise ValueError(f"{case_id}: only a failed trajectory may declare an errorCode")
    if expected.status != "failed" and expected.trace and expected.trace[-1].startswith("failed"):
        raise ValueError(f"{case_id}: a non-failed trajectory must not end with a failed event")

    if expected.workflow_invocations > len(case.planned_requests):
        raise ValueError(
            f"{case_id}: workflow invocations cannot exceed the declared planned requests"
        )
    for plan in case.planned_requests:
        if plan.request_payload.get("kind") not in _TOOL_REQUEST_REQUEST_TYPE:
            raise ValueError(
                f"{case_id}: planned request for {plan.tool} has an invalid request kind"
            )
    if case.family == "completed_single" and len(case.planned_requests) != 1:
        raise ValueError(f"{case_id}: completed_single requires exactly one planned request")


def _parse_shapes(value: object, *, line_number: int) -> tuple[CareerTrajectoryShape, ...]:
    if not isinstance(value, list):
        raise ValueError(
            f"Trajectory Eval line {line_number} field shapes must be an array"
        )
    shapes: list[CareerTrajectoryShape] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(
                f"Trajectory Eval line {line_number} shapes entries must be strings"
            )
        try:
            shapes.append(CareerTrajectoryShape(item))
        except ValueError as exc:
            raise ValueError(
                f"Trajectory Eval line {line_number} references unknown PRD shape {item!r}"
            ) from exc
    return tuple(shapes)


def _parse_plan(payload: object, *, line_number: int, index: int) -> CareerTrajectoryEvalPlan:
    plan_payload = _object(payload, field=f"plannedRequests[{index}]", line_number=line_number)
    tool = _required_string(plan_payload, "tool", line_number=line_number)
    try:
        CareerAgentToolName(tool)
    except ValueError as exc:
        raise ValueError(
            f"Trajectory Eval line {line_number} plannedRequests[{index}] references unknown "
            f"tool {tool!r}"
        ) from exc

    params_payload = plan_payload.get("normalizedParams", [])
    if not isinstance(params_payload, list):
        raise ValueError(
            f"Trajectory Eval line {line_number} normalizedParams must be an array"
        )
    params: list[tuple[str, str]] = []
    for entry in params_payload:
        if (
            not isinstance(entry, list)
            or len(entry) != 2
            or not isinstance(entry[0], str)
            or not isinstance(entry[1], str)
        ):
            raise ValueError(
                f"Trajectory Eval line {line_number} normalizedParams entries must be "
                "[key, value] pairs"
            )
        params.append((entry[0], entry[1]))

    return CareerTrajectoryEvalPlan(
        tool=tool,
        fact_fingerprint=_required_string(plan_payload, "factFingerprint", line_number=line_number),
        normalized_params=tuple(params),
        request_payload=_object(
            plan_payload.get("request"),
            field=f"plannedRequests[{index}].request",
            line_number=line_number,
        ),
        expected_provider_calls=_optional_int(
            plan_payload.get("expectedProviderCalls", 0), line_number=line_number
        ),
        business_writes=_optional_int(
            plan_payload.get("businessWrites", 0), line_number=line_number
        ),
        external_effects=tuple(
            _string_list_field(
                plan_payload.get("externalEffects", []),
                field="externalEffects",
                line_number=line_number,
            )
        ),
        expires_at=_optional_string(
            plan_payload.get("expiresAt"),
            field="expiresAt",
            line_number=line_number,
        ),
    )


def _parse_budget(payload: object, *, line_number: int) -> dict[str, int]:
    budget_payload = _object(payload, field="budget", line_number=line_number)
    overrides: dict[str, int] = {}
    for key, value in budget_payload.items():
        if key not in _BUDGET_FIELDS:
            raise ValueError(
                f"Trajectory Eval line {line_number} budget has unknown field {key!r}"
            )
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"Trajectory Eval line {line_number} budget field {key} must be int"
            )
        overrides[key] = value
    return overrides


def _required_string(payload: Mapping[str, object], field: str, *, line_number: int) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Trajectory Eval line {line_number} requires non-empty {field}")
    return value


def _optional_string(value: object, *, field: str, line_number: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Trajectory Eval line {line_number} field {field} must be non-empty str | null"
        )
    return value


def _optional_bool(value: object, *, line_number: int) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Trajectory Eval line {line_number} field usable must be bool")
    return value


def _optional_int(value: object, *, line_number: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Trajectory Eval line {line_number} field must be int")
    return value


def _required_int(payload: Mapping[str, object], field: str, *, line_number: int) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Trajectory Eval line {line_number} field {field} must be int")
    return value


def _object(value: object, *, field: str, line_number: int) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(
            f"Trajectory Eval line {line_number} field {field} must be an object"
        )
    return value


def _string_list_field(value: object, *, field: str, line_number: int) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(
            f"Trajectory Eval line {line_number} field {field} must be a string array"
        )
    return list(value)


__all__ = [
    "CareerTrajectoryEvalCase",
    "CareerTrajectoryEvalCaseResult",
    "CareerTrajectoryEvalContext",
    "CareerTrajectoryEvalDriver",
    "CareerTrajectoryEvalExecution",
    "CareerTrajectoryEvalExpected",
    "CareerTrajectoryEvalPlan",
    "CareerTrajectoryEvalReport",
    "CareerTrajectoryShape",
    "CareerTrajectoryShapeCoverage",
    "CareerTrajectoryShapeStatus",
    "career_trajectory_shape_coverage",
    "evaluate_career_trajectories",
    "load_career_trajectory_eval_dataset",
    "validate_career_trajectory_release_dataset",
]
