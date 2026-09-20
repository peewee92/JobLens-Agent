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
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from app.agent.context import (
    CareerAgentContext,
    CareerAgentJobContext,
    CareerAgentProfileContext,
)
from app.agent.execution_gate import CareerAgentGovernedToolExecutor
from app.agent.governed_loop_runtime import (
    CareerAgentGovernedLoopResult,
    CareerAgentGovernedLoopRuntime,
    CareerAgentGovernedLoopStatus,
    CareerAgentLoopRecoveryPlanner,
    CareerAgentPlannedToolRequest,
    CareerAgentStalenessGuard,
    CareerAgentUnknownToolReplanner,
)
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.hitl_service import (
    CareerAgentHitlService,
    ResumeCareerAgentRunRequest,
)
from app.agent.graph.state import CareerAgentState
from app.agent.intent import (
    CareerIntent,
    CareerIntentGoal,
    CareerIntentResolutionContext,
    CareerIntentRouter,
)
from app.agent.runtime_dispatch import (
    CareerAgentDurableRunIdentity,
    CareerAgentRuntimeDispatchError,
    CareerAgentRuntimeDispatchKind,
    CareerAgentRuntimeDispatchRequest,
    CareerAgentRuntimeDispatcher,
)
from app.agent.tool_loop import CareerAgentLoopBudget
from app.agent.tool_registry import (
    CareerAgentToolError,
    CareerAgentToolName,
    CareerAgentToolRegistry,
    CareerAgentToolRequest,
    JobPreparationRequest,
    RankMatchReportsRequest,
    TargetCohortGapsRequest,
)
from app.agent.tool_selection import CareerAgentToolSelector
from app.application.match_report.models import (
    MatchRecommendation,
    MatchReport,
    StoredMatchReport,
)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

_TRACE_VOCABULARY = frozenset(
    {
        "intent_routed",
        "clarification",
        "unsupported",
        "blocked",
        "recovery",
        "tool_selected",
        "tool_called",
        "pending_action",
        "tool_result",
        "failed",
        "cancelled",
        "finished",
    }
)

_TOOL_REQUEST_REQUEST_TYPE: dict[str, type[object]] = {
    "rank_match_reports": RankMatchReportsRequest,
    "target_cohort_gaps": TargetCohortGapsRequest,
    "job_preparation": JobPreparationRequest,
}

_TOOL_REQUIRED_EVENTS = ("tool_selected", "tool_called", "pending_action", "tool_result")
_TOOL_OPTIONAL_EVENTS = ("failed", "cancelled", "recovery")

_DURABLE_DISPATCH_EVENTS = frozenset(
    {
        "dispatch",
        "start",
        "step",
        "interrupt",
        "ranking",
        "gaps",
        "governed",
        "resume",
        "resume_step",
        "confirmed",
        "provider",
        "dispatch_error",
    }
)

_DRIVERS = ("governed_loop", "durable_dispatch")


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
        status=CareerTrajectoryShapeStatus.COVERED,
        evidence=(
            "cohort: rank+gaps intent -> CareerAgentRuntimeDispatcher -> real "
            "CareerAgentHitlService over SQLite -> Ranking -> durable interrupt -> "
            "approve/reject -> stale validation -> Gap, with the governed loop never "
            "invoked (governed=0)"
        ),
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.RANKING_GAP_PREPARATION,
        status=CareerTrajectoryShapeStatus.COVERED,
        evidence="probe: status=completed, three ordered tool cycles then finished",
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.TOOL_EMPTY_CLARIFICATION,
        status=CareerTrajectoryShapeStatus.COVERED,
        evidence=(
            "cohort: empty goals -> status=clarification_required, "
            "trace=intent_routed > clarification"
        ),
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.INVALID_PARAMS_CORRECTED_RETRY,
        status=CareerTrajectoryShapeStatus.COVERED,
        evidence=(
            "cohort: malformed args -> recovery event -> corrected plan executes, "
            "trace=intent_routed > tool_selected:X > recovery:X > tool_called:X > "
            "tool_result:X > finished"
        ),
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.TRANSIENT_ERROR_BOUNDED_RETRY,
        status=CareerTrajectoryShapeStatus.COVERED,
        evidence=(
            "cohort: workflow raises ConnectionError once -> recovery event -> retry succeeds; "
            "second failure terminates with transient_network"
        ),
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.UNKNOWN_TOOL_REPLAN,
        status=CareerTrajectoryShapeStatus.COVERED,
        evidence=(
            "cohort: unknown goal -> recovery event (no tool) -> replanned goals resolve; "
            "exhausted replan terminates with unknown_tool"
        ),
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.SAME_TOOL_LOOP_STOPPED,
        status=CareerTrajectoryShapeStatus.COVERED,
        evidence="probe: duplicated goal -> status=failed, error_code=loop_detected, one workflow call only",
    ),
    CareerTrajectoryShapeCoverage(
        shape=CareerTrajectoryShape.STALE_TERMINATE,
        status=CareerTrajectoryShapeStatus.COVERED,
        evidence=(
            "cohort: stale before execution -> failed/stale_state without touching a workflow; "
            "stale detected after a transient recovery also terminates before re-execution"
        ),
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
    "tool_empty": 2,
    "unsupported": 2,
    "blocked": 2,
    "invalid_intent_output": 2,
    "invalid_tool_params": 4,
    "loop_detected": 2,
    "budget_exhausted": 2,
    "transient_retry": 3,
    "corrected_retry": 3,
    "unknown_tool_replan": 3,
    "stale_terminate": 3,
    "runtime_timeout": 2,
    "run_cancelled": 2,
    "durable_dispatch": 8,
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
class CareerTrajectoryEvalDispatchConfig:
    """Frozen inputs for the durable HITL dispatch leg.

    The resume is always performed through a freshly constructed
    ``CareerAgentHitlService`` over the same SQLite checkpoint store, so a
    surviving interrupt is real durable persistence rather than in-memory state.
    """

    thread_id: str
    run_id: str
    request_id: str
    top_n: int = 5
    resume_decision: str | None = None
    selected_job_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CareerTrajectoryEvalDispatchExpected:
    """Assertions on the dispatch handoff, observed from real durable state."""

    dispatch_kind: str
    start_status: str | None = None
    start_step: str | None = None
    interrupt_persisted: bool = False
    proposed_target_job_ids: tuple[str, ...] = ()
    resume_status: str | None = None
    resume_step: str | None = None
    confirmed_target_job_ids: tuple[str, ...] = ()
    ranking_invocations: int = 0
    gap_invocations: int = 0
    governed_loop_invocations: int = 0
    provider_calls: int = 0
    dispatch_error_kind: str | None = None
    dispatch_error_contains: str | None = None
    resumed_by_fresh_service: bool = False


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
    stale_checks: tuple[bool, ...] = ()
    transient_faults: Mapping[str, tuple[bool, ...]] = field(default_factory=dict)
    recovery_plans: tuple[CareerTrajectoryEvalPlan, ...] = ()
    replan_goals: tuple[tuple[str, ...], ...] = ()
    clock_script: tuple[float, ...] = ()
    cancel_after_checks: int | None = None
    driver: str = "governed_loop"
    dispatch: CareerTrajectoryEvalDispatchConfig | None = None
    dispatch_expected: CareerTrajectoryEvalDispatchExpected | None = None


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
    dispatch: CareerTrajectoryEvalDispatchExpected | None = None
    runtime_latency_ms: float = 0.0
    terminal_reason: str | None = None


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


class _FaultingWorkflow:
    """Record-only workflow that can raise a scripted transient failure per attempt."""

    def __init__(self, faults: tuple[bool, ...], label: str) -> None:
        self._faults = faults
        self._label = label
        self.calls = 0

    @property
    def invoked(self) -> int:
        return self.calls

    def _advance(self) -> None:
        index = self.calls
        self.calls += 1
        if index < len(self._faults) and self._faults[index]:
            raise ConnectionError(f"simulated transient network failure in {self._label}")


class _FaultingRanking(_FaultingWorkflow):
    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        include_blocked: bool = False,
        top_n: int | None = None,
    ) -> object:
        self._advance()
        return {"jobIds": list(job_ids)}


class _FaultingGaps(_FaultingWorkflow):
    def execute(self, command: object) -> object:
        self._advance()
        return {"cohortId": getattr(command, "cohort_id", None)}


class _FaultingPreparation(_FaultingWorkflow):
    def execute(self, job_id: str) -> object:
        self._advance()
        return {"jobId": job_id}


class _ScriptedStalenessGuard:
    """Consume a frozen staleness script; anything past the script is fresh."""

    def __init__(self, script: tuple[bool, ...]) -> None:
        self._script = script
        self.calls = 0

    def is_stale(
        self,
        *,
        context: CareerAgentContext,
        plan: CareerAgentPlannedToolRequest,
    ) -> bool:
        index = self.calls
        self.calls += 1
        return self._script[index] if index < len(self._script) else False


class _ScriptedRecoveryPlanner:
    """Return frozen corrected plans in order, then refuse further recovery."""

    def __init__(self, plans: tuple[CareerAgentPlannedToolRequest, ...]) -> None:
        self._plans = plans
        self.calls = 0

    def recover_tool_request(
        self,
        *,
        tool: CareerAgentToolName,
        error_code: str,
        previous_plan: CareerAgentPlannedToolRequest | None,
        attempt: int,
    ) -> CareerAgentPlannedToolRequest | None:
        if self.calls >= len(self._plans):
            return None
        plan = self._plans[self.calls]
        self.calls += 1
        return plan


class _ScriptedUnknownToolReplanner:
    """Return frozen goal sets in order, then refuse further replanning."""

    def __init__(self, goal_sets: tuple[tuple[CareerIntentGoal, ...], ...]) -> None:
        self._goal_sets = goal_sets
        self.calls = 0

    def replan_unknown_tool(
        self,
        *,
        previous_goals: tuple[CareerIntentGoal, ...],
        attempt: int,
    ) -> tuple[CareerIntentGoal, ...] | None:
        if self.calls >= len(self._goal_sets):
            return None
        goals = self._goal_sets[self.calls]
        self.calls += 1
        return goals


class _ScriptedClock:
    """Virtual monotonic clock; values are consumed in order, last one repeats.

    Cases using a virtual clock cannot report a real latency, so the latency
    baseline excludes them explicitly instead of publishing virtual numbers.
    """

    def __init__(self, script: tuple[float, ...]) -> None:
        self._script = script
        self.calls = 0

    def __call__(self) -> float:
        index = self.calls
        self.calls += 1
        if index < len(self._script):
            return self._script[index]
        return self._script[-1]


class _ScriptedCancellation:
    """Report cancelled only after the first ``after`` checks."""

    def __init__(self, after: int) -> None:
        self._after = after
        self.calls = 0

    def is_cancelled(self) -> bool:
        self.calls += 1
        return self.calls > self._after


class _DispatchContextBuilder:
    """Minimal governed context for the durable HITL fixture."""

    def build(self) -> CareerAgentContext:
        return CareerAgentContext(
            usable=True,
            confirmation_boundary="confirmed",
            profile=CareerAgentProfileContext(
                id="profile_1",
                version=3,
                headline="Eval fixture profile",
                years_of_experience=8,
                skills=(),
            ),
            search_intent=None,
            current_job=None,
            relevant_evidence=(),
            blockers=(),
            blocker_messages=(),
        )


class _DispatchRankingWorkflow:
    """Return grounded MatchReports for the requested jobs, counting invocations."""

    def __init__(self, job_ids: tuple[str, ...]) -> None:
        self._job_ids = job_ids
        self.calls = 0

    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        include_blocked: bool = False,
        top_n: int | None = None,
    ) -> object:
        self.calls += 1
        rows = tuple(
            _stored_report(job_id)
            for job_id in self._job_ids
            if job_id in set(job_ids)
        )
        return rows if top_n is None else rows[:top_n]


class _DispatchGapWorkflow:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, command: object) -> object:
        self.calls += 1
        return _DispatchGapResult(
            cohort_id=getattr(command, "cohort_id", ""),
            job_ids=tuple(getattr(command, "selected_job_ids", ()) or ()),
        )


class _UnusedDispatchWorkflow:
    def execute(self, *args: object, **kwargs: object) -> object:  # pragma: no cover
        raise AssertionError("unrelated workflow must not run during dispatch eval")


class _GovernedLoopSpy:
    """Record whether the dispatcher wrongly fell back to the governed loop."""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, **kwargs: object) -> CareerAgentGovernedLoopResult:
        self.calls += 1
        return CareerAgentGovernedLoopResult(
            status=CareerAgentGovernedLoopStatus.COMPLETED,
            tool_results=(),
            trace=(),
        )


@dataclass(frozen=True, slots=True)
class _DispatchGapResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool = True
    blockers: tuple[str, ...] = ()
    provider_calls: int = 0
    db_writes: int = 0


def _stored_report(job_id: str) -> StoredMatchReport:
    return StoredMatchReport(
        id=f"mr_{job_id}",
        report=MatchReport(
            job_id=job_id,
            profile_id="profile_1",
            profile_version=3,
            extraction_id=f"ext_{job_id}",
            eligibility=None,  # type: ignore[arg-type]
            recommendation=MatchRecommendation.STRONG,
            summary="grounded",
            strengths=(),
            risks=(),
            requirement_results=(),
            matched_requirement_ids=(),
            partial_requirement_ids=(),
            missing_requirement_ids=(),
            evidence_links=(),
            matcher_version="eval_fixture",
            prompt_version="eval_fixture",
            model=None,
            trace_run_id=None,
        ),
        created_at=datetime.now(UTC),
    )


class CareerTrajectoryEvalDriver:
    """Drive the frozen Core runtime chain over frozen trajectory cases.

    For ``governed_loop`` cases the driver drives ``CareerAgentGovernedLoopRuntime``.
    For ``durable_dispatch`` cases it drives the real ``CareerAgentRuntimeDispatcher``
    into the real ``CareerAgentHitlService`` over a throwaway SQLite checkpoint
    store, then resumes through a *second* service instance so the durable
    interrupt is proven to survive the service being replaced.

    The driver contains no routing, planner, staleness, or retry logic of its own;
    every such decision stays in Core and is observed from real state.
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
        if case.driver == "durable_dispatch":
            return self._drive_durable_dispatch(case)
        return self._drive_governed_loop(case)

    def _drive_durable_dispatch(
        self,
        case: CareerTrajectoryEvalCase,
    ) -> CareerTrajectoryEvalExecution:
        config = case.dispatch
        assert config is not None
        started_at = time.perf_counter()

        with tempfile.TemporaryDirectory() as workspace:
            checkpoint_path = Path(workspace) / "durable-dispatch.sqlite3"
            ranking = _DispatchRankingWorkflow(case.context.run_job_ids)
            gaps = _DispatchGapWorkflow()
            governed = _GovernedLoopSpy()
            registry = CareerAgentToolRegistry(
                ranking=ranking,
                target_cohort_gaps=gaps,  # type: ignore[arg-type]
                job_preparation=_UnusedDispatchWorkflow(),
            )
            dispatcher = CareerAgentRuntimeDispatcher(
                governed_runtime=governed,  # type: ignore[arg-type]
                hitl_service=_build_hitl_service(checkpoint_path, registry),
            )

            dispatch_error_kind: str | None = None
            dispatch_error_message: str | None = None
            try:
                dispatched = dispatcher.run(
                    CareerAgentRuntimeDispatchRequest(
                        user_message=case.message,
                        intent=_build_intent(case.intent_payload),
                        context=_DispatchContextBuilder().build(),
                        resolution_context=CareerIntentResolutionContext(
                            current_job_id=case.context.current_job_id,
                            run_job_ids=case.context.run_job_ids,
                        ),
                        durable_run=CareerAgentDurableRunIdentity(
                            thread_id=config.thread_id,
                            run_id=config.run_id,
                            request_id=config.request_id,
                            top_n=config.top_n,
                        ),
                    )
                )
            except CareerAgentRuntimeDispatchError as exc:
                dispatch_error_kind = "dispatch_error"
                dispatch_error_message = str(exc)
                dispatched = None
            except ValueError as exc:
                dispatch_error_kind = type(exc).__name__
                dispatch_error_message = str(exc)
                dispatched = None

            if dispatched is None:
                return CareerTrajectoryEvalExecution(
                    status=dispatch_error_kind,
                    error_code=None,
                    trace=("dispatch_error",),
                    trace_fingerprints=("dispatch_error",),
                    tool_results=0,
                    workflow_invocations=ranking.calls + gaps.calls,
                    pending_action_present=False,
                    replay_stable=True,
                    dispatch=CareerTrajectoryEvalDispatchExpected(
                        dispatch_kind="none",
                        ranking_invocations=ranking.calls,
                        gap_invocations=gaps.calls,
                        governed_loop_invocations=governed.calls,
                        dispatch_error_kind=dispatch_error_kind,
                        dispatch_error_contains=dispatch_error_message,
                    ),
                    runtime_latency_ms=_elapsed_ms(started_at),
                    terminal_reason=dispatch_error_kind,
                )

            observed = _observe_dispatch(
                dispatched=dispatched,
                ranking=ranking,
                gaps=gaps,
                governed=governed,
                dispatched_kind=dispatched.kind.value,
            )

            if (
                config.resume_decision is not None
                and dispatched.durable_state is not None
                and dispatched.durable_state.interrupt_id is not None
            ):
                # Resume through a freshly constructed service so a surviving
                # interrupt proves real durable persistence, not in-memory state.
                resumed = _build_hitl_service(checkpoint_path, registry).resume(
                    ResumeCareerAgentRunRequest(
                        thread_id=config.thread_id,
                        interrupt_id=dispatched.durable_state.interrupt_id,
                        action_id=f"eval-{case.case_id}",
                        decision=config.resume_decision,  # type: ignore[arg-type]
                        selected_job_ids=config.selected_job_ids,
                    )
                )
                observed = replace(
                    observed,
                    resume_status=resumed.status.value,
                    resume_step=resumed.current_step,
                    confirmed_target_job_ids=tuple(resumed.confirmed_target_job_ids),
                    provider_calls=resumed.provider_call_count,
                    ranking_invocations=ranking.calls,
                    gap_invocations=gaps.calls,
                    governed_loop_invocations=governed.calls,
                    resumed_by_fresh_service=True,
                )

            trace = _render_dispatch_trace(observed)
            return CareerTrajectoryEvalExecution(
                status=observed.dispatch_kind,
                error_code=None,
                trace=trace,
                trace_fingerprints=trace,
                tool_results=0,
                workflow_invocations=observed.ranking_invocations + observed.gap_invocations,
                pending_action_present=False,
                replay_stable=True,
                dispatch=observed,
                runtime_latency_ms=_elapsed_ms(started_at),
                terminal_reason=observed.dispatch_kind,
            )

    def _drive_governed_loop(
        self,
        case: CareerTrajectoryEvalCase,
    ) -> CareerTrajectoryEvalExecution:
        def faults_for(tool: CareerAgentToolName) -> tuple[bool, ...]:
            return tuple(case.transient_faults.get(tool.value, ()))

        ranking = _FaultingRanking(faults_for(CareerAgentToolName.RANK_MATCH_REPORTS), "ranking")
        gaps = _FaultingGaps(faults_for(CareerAgentToolName.TARGET_COHORT_GAPS), "gaps")
        preparation = _FaultingPreparation(faults_for(CareerAgentToolName.JOB_PREPARATION), "prep")
        registry = CareerAgentToolRegistry(
            ranking=ranking,
            target_cohort_gaps=gaps,
            job_preparation=preparation,
        )
        runtime = CareerAgentGovernedLoopRuntime(
            router=CareerIntentRouter(model=_ReplayIntentModel({case.message: case.intent_payload})),
            selector=CareerAgentToolSelector(registry=registry),
            executor=CareerAgentGovernedToolExecutor(registry=registry),
            staleness_guard=_ScriptedStalenessGuard(case.stale_checks),
            budget=replace(CareerAgentLoopBudget(), **dict(case.budget_overrides)),
            recovery_planner=(
                _ScriptedRecoveryPlanner(
                    tuple(_build_plan(plan) for plan in case.recovery_plans)
                )
                if case.recovery_plans
                else None
            ),
            unknown_tool_replanner=(
                _ScriptedUnknownToolReplanner(
                    tuple(
                        tuple(CareerIntentGoal(goal) for goal in goals)
                        for goals in case.replan_goals
                    )
                )
                if case.replan_goals
                else None
            ),
            monotonic_clock=_ScriptedClock(case.clock_script) if case.clock_script else None,
            cancellation_signal=(
                _ScriptedCancellation(case.cancel_after_checks)
                if case.cancel_after_checks is not None
                else None
            ),
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
            workflow_invocations=ranking.invoked + gaps.invoked + preparation.invoked,
            pending_action_present=result.pending_action is not None,
            replay_stable=True,
            trace_leak=leak,
            runtime_latency_ms=result.runtime_latency_ms,
            terminal_reason=result.terminal_reason,
        )


def _elapsed_ms(started_at: float) -> float:
    return max(0.0, (time.perf_counter() - started_at) * 1000.0)


def _build_hitl_service(
    checkpoint_path: Path,
    registry: CareerAgentToolRegistry,
) -> CareerAgentHitlService:
    """Build a real durable HITL service over a throwaway SQLite store."""

    return CareerAgentHitlService(
        checkpoints=SQLiteCareerAgentCheckpointStore(checkpoint_path),
        context_builder=_DispatchContextBuilder(),  # type: ignore[arg-type]
        tool_registry=registry,
    )


def _build_intent(payload: Mapping[str, object]) -> CareerIntent:
    goals = tuple(CareerIntentGoal(goal) for goal in payload.get("goals", ()))  # type: ignore[arg-type]
    referenced = tuple(payload.get("referenced_job_ids", ()))  # type: ignore[arg-type]
    return CareerIntent(goals=goals, referenced_job_ids=referenced)


def _observe_dispatch(
    *,
    dispatched: object,
    ranking: _DispatchRankingWorkflow,
    gaps: _DispatchGapWorkflow,
    governed: _GovernedLoopSpy,
    dispatched_kind: str,
) -> CareerTrajectoryEvalDispatchExpected:
    """Read the dispatch outcome from real state, not from declared intent."""

    state = getattr(dispatched, "durable_state", None)
    start_status: str | None = None
    start_step: str | None = None
    interrupt_persisted = False
    proposed: tuple[str, ...] = ()
    if state is not None:
        start_status = state.status.value
        start_step = state.current_step
        interrupt_persisted = state.interrupt_id is not None
        proposed = tuple(state.proposed_target_job_ids)
        provider_calls = state.provider_call_count
    else:
        provider_calls = 0

    return CareerTrajectoryEvalDispatchExpected(
        dispatch_kind=dispatched_kind,
        start_status=start_status,
        start_step=start_step,
        interrupt_persisted=interrupt_persisted,
        proposed_target_job_ids=proposed,
        ranking_invocations=ranking.calls,
        gap_invocations=gaps.calls,
        governed_loop_invocations=governed.calls,
        provider_calls=provider_calls,
    )


def _render_dispatch_trace(observed: CareerTrajectoryEvalDispatchExpected) -> tuple[str, ...]:
    """Render the observed dispatch facts as an ordered, replay-checkable trace."""

    trace = [
        f"dispatch:{observed.dispatch_kind}",
        f"ranking:{observed.ranking_invocations}",
        f"gaps:{observed.gap_invocations}",
        f"governed:{observed.governed_loop_invocations}",
        f"provider:{observed.provider_calls}",
    ]
    if observed.start_status is not None:
        trace.insert(1, f"start:{observed.start_status}")
        trace.insert(2, f"step:{observed.start_step}")
        trace.insert(3, f"interrupt:{'present' if observed.interrupt_persisted else 'absent'}")
    if observed.resume_status is not None:
        trace.append(f"resume:{observed.resume_status}")
        trace.append(f"resume_step:{observed.resume_step}")
        trace.append("confirmed:" + "|".join(observed.confirmed_target_job_ids))
    return tuple(trace)


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
    if case.driver == "governed_loop" and execution.trace != expected.trace:
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
    _assert_dispatch_matches(case=case, execution=execution, failures=failures)


def _assert_dispatch_matches(
    *,
    case: CareerTrajectoryEvalCase,
    execution: CareerTrajectoryEvalExecution,
    failures: list[str],
) -> None:
    if case.driver != "durable_dispatch":
        if execution.dispatch is not None:
            failures.append("only a durable_dispatch case may report dispatch observations")
        return

    expected = case.dispatch_expected
    observed = execution.dispatch
    if expected is None:
        failures.append("a durable_dispatch case requires expected.dispatch")
        return
    if observed is None:
        failures.append("durable_dispatch execution must report dispatch observations")
        return

    for field_name in (
        "dispatch_kind",
        "start_status",
        "start_step",
        "interrupt_persisted",
        "proposed_target_job_ids",
        "resume_status",
        "resume_step",
        "confirmed_target_job_ids",
        "ranking_invocations",
        "gap_invocations",
        "governed_loop_invocations",
        "provider_calls",
        "dispatch_error_kind",
    ):
        actual_value = getattr(observed, field_name)
        expected_value = getattr(expected, field_name)
        if actual_value != expected_value:
            failures.append(
                f"dispatch.{field_name} expected {expected_value!r}, got {actual_value!r}"
            )

    if (
        expected.dispatch_error_contains is not None
        and (
            observed.dispatch_error_contains is None
            or expected.dispatch_error_contains not in observed.dispatch_error_contains
        )
    ):
        failures.append(
            "dispatch error message must contain "
            f"{expected.dispatch_error_contains!r}, got {observed.dispatch_error_contains!r}"
        )

    for event in execution.trace:
        name = event.split(":", 1)[0]
        if name not in _DURABLE_DISPATCH_EVENTS:
            failures.append(f"dispatch trace event {event!r} is not in the dispatch vocabulary")


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
    recovery_payload = payload.get("recoveryPlans", [])
    if not isinstance(recovery_payload, list):
        raise ValueError(
            f"Trajectory Eval line {line_number} field recoveryPlans must be an array"
        )
    recovery_plans = tuple(
        _parse_plan(item, line_number=line_number, index=index, field_name="recoveryPlans")
        for index, item in enumerate(recovery_payload)
    )
    budget_overrides = _parse_budget(payload.get("budget", {}), line_number=line_number)
    driver = str(payload.get("driver", "governed_loop"))
    if driver not in _DRIVERS:
        raise ValueError(
            f"Trajectory Eval line {line_number} has unknown driver {driver!r}"
        )
    dispatch = _parse_dispatch_config(
        payload.get("dispatch"),
        line_number=line_number,
        case_id=case_id,
    )
    stale_checks = _parse_bool_list(
        payload.get("staleChecks", []),
        field="staleChecks",
        line_number=line_number,
    )
    transient_faults = _parse_transient_faults(
        payload.get("transientFaults", {}),
        line_number=line_number,
    )
    replan_goals = _parse_replan_goals(
        payload.get("replanGoals", []),
        line_number=line_number,
    )
    clock_script = _parse_float_list(
        payload.get("clockScript", []),
        field="clockScript",
        line_number=line_number,
    )
    cancel_after_raw = payload.get("cancelAfterChecks")
    if cancel_after_raw is not None and (
        isinstance(cancel_after_raw, bool) or not isinstance(cancel_after_raw, int)
    ):
        raise ValueError(
            f"Trajectory Eval line {line_number} field cancelAfterChecks must be int | null"
        )

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
        stale_checks=stale_checks,
        transient_faults=transient_faults,
        recovery_plans=recovery_plans,
        replan_goals=replan_goals,
        clock_script=clock_script,
        cancel_after_checks=cancel_after_raw,
        driver=driver,
        dispatch=dispatch,
        dispatch_expected=_parse_dispatch_expected(
            expected_payload.get("dispatch"),
            line_number=line_number,
            case_id=case_id,
        ),
    )
    _validate_case_semantics(case)
    return case


def _parse_dispatch_config(
    payload: object,
    *,
    line_number: int,
    case_id: str,
) -> CareerTrajectoryEvalDispatchConfig | None:
    if payload is None:
        return None
    config_payload = _object(payload, field="dispatch", line_number=line_number)
    decision = _optional_string(
        config_payload.get("resume"),
        field="dispatch.resume",
        line_number=line_number,
    )
    if decision is not None and decision not in ("approve", "edit", "reject"):
        raise ValueError(
            f"{case_id}: dispatch.resume must be approve, edit, or reject"
        )
    top_n = config_payload.get("topN", 5)
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ValueError(f"{case_id}: dispatch.topN must be a positive int")
    return CareerTrajectoryEvalDispatchConfig(
        thread_id=_required_string(config_payload, "threadId", line_number=line_number),
        run_id=_required_string(config_payload, "runId", line_number=line_number),
        request_id=_required_string(config_payload, "requestId", line_number=line_number),
        top_n=top_n,
        resume_decision=decision,
        selected_job_ids=tuple(
            _string_list_field(
                config_payload.get("selectedJobIds", []),
                field="dispatch.selectedJobIds",
                line_number=line_number,
            )
        ),
    )


def _parse_dispatch_expected(
    payload: object,
    *,
    line_number: int,
    case_id: str,
) -> CareerTrajectoryEvalDispatchExpected | None:
    if payload is None:
        return None
    expected_payload = _object(payload, field="expected.dispatch", line_number=line_number)
    return CareerTrajectoryEvalDispatchExpected(
        dispatch_kind=_required_string(
            expected_payload, "dispatchKind", line_number=line_number
        ),
        start_status=_optional_string(
            expected_payload.get("startStatus"),
            field="expected.dispatch.startStatus",
            line_number=line_number,
        ),
        start_step=_optional_string(
            expected_payload.get("startStep"),
            field="expected.dispatch.startStep",
            line_number=line_number,
        ),
        interrupt_persisted=_required_bool(
            expected_payload, "interruptPersisted", line_number=line_number
        ),
        proposed_target_job_ids=tuple(
            _string_list_field(
                expected_payload.get("proposedTargetJobIds", []),
                field="expected.dispatch.proposedTargetJobIds",
                line_number=line_number,
            )
        ),
        resume_status=_optional_string(
            expected_payload.get("resumeStatus"),
            field="expected.dispatch.resumeStatus",
            line_number=line_number,
        ),
        resume_step=_optional_string(
            expected_payload.get("resumeStep"),
            field="expected.dispatch.resumeStep",
            line_number=line_number,
        ),
        confirmed_target_job_ids=tuple(
            _string_list_field(
                expected_payload.get("confirmedTargetJobIds", []),
                field="expected.dispatch.confirmedTargetJobIds",
                line_number=line_number,
            )
        ),
        ranking_invocations=_required_int(
            expected_payload, "rankingInvocations", line_number=line_number
        ),
        gap_invocations=_required_int(
            expected_payload, "gapInvocations", line_number=line_number
        ),
        governed_loop_invocations=_required_int(
            expected_payload, "governedLoopInvocations", line_number=line_number
        ),
        provider_calls=_required_int(
            expected_payload, "providerCalls", line_number=line_number
        ),
        dispatch_error_kind=_optional_string(
            expected_payload.get("dispatchErrorKind"),
            field="expected.dispatch.dispatchErrorKind",
            line_number=line_number,
        ),
        dispatch_error_contains=_optional_string(
            expected_payload.get("dispatchErrorContains"),
            field="expected.dispatch.dispatchErrorContains",
            line_number=line_number,
        ),
    )


def _parse_bool_list(value: object, *, field: str, line_number: int) -> tuple[bool, ...]:
    if not isinstance(value, list) or not all(isinstance(item, bool) for item in value):
        raise ValueError(
            f"Trajectory Eval line {line_number} field {field} must be a boolean array"
        )
    return tuple(value)


def _parse_float_list(value: object, *, field: str, line_number: int) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise ValueError(
            f"Trajectory Eval line {line_number} field {field} must be a numeric array"
        )
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(
                f"Trajectory Eval line {line_number} field {field} must be a numeric array"
            )
        numbers.append(float(item))
    return tuple(numbers)


def _parse_transient_faults(
    value: object,
    *,
    line_number: int,
) -> dict[str, tuple[bool, ...]]:
    payload = _object(value, field="transientFaults", line_number=line_number)
    faults: dict[str, tuple[bool, ...]] = {}
    for tool, flags in payload.items():
        try:
            CareerAgentToolName(tool)
        except ValueError as exc:
            raise ValueError(
                f"Trajectory Eval line {line_number} transientFaults references unknown tool "
                f"{tool!r}"
            ) from exc
        faults[tool] = _parse_bool_list(
            flags,
            field=f"transientFaults.{tool}",
            line_number=line_number,
        )
    return faults


def _parse_replan_goals(
    value: object,
    *,
    line_number: int,
) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list):
        raise ValueError(
            f"Trajectory Eval line {line_number} field replanGoals must be an array"
        )
    goal_sets: list[tuple[str, ...]] = []
    for entry in value:
        if not isinstance(entry, list) or not all(isinstance(item, str) for item in entry):
            raise ValueError(
                f"Trajectory Eval line {line_number} replanGoals entries must be string arrays"
            )
        for goal in entry:
            try:
                CareerIntentGoal(goal)
            except ValueError as exc:
                raise ValueError(
                    f"Trajectory Eval line {line_number} replanGoals references unknown goal "
                    f"{goal!r}"
                ) from exc
        goal_sets.append(tuple(entry))
    return tuple(goal_sets)


def _validate_case_semantics(case: CareerTrajectoryEvalCase) -> None:
    case_id = case.case_id
    expected = case.expected

    if case.driver == "durable_dispatch":
        _validate_dispatch_case(case)
        return

    if case.dispatch is not None or case.dispatch_expected is not None:
        raise ValueError(
            f"{case_id}: only a durable_dispatch case may declare dispatch fields"
        )
    _validate_governed_loop_case(case)
    _validate_injection_case(case)


def _validate_dispatch_case(case: CareerTrajectoryEvalCase) -> None:
    case_id = case.case_id
    expected = case.expected

    if case.dispatch is None:
        raise ValueError(f"{case_id}: durable_dispatch case requires a dispatch config")
    if case.dispatch_expected is None:
        raise ValueError(f"{case_id}: durable_dispatch case requires expected.dispatch")
    if expected.trace:
        raise ValueError(
            f"{case_id}: durable_dispatch traces are derived from observed state and must "
            "not be declared"
        )
    if expected.error_code is not None:
        raise ValueError(f"{case_id}: durable_dispatch case must not declare an errorCode")
    if expected.tool_results != 0:
        raise ValueError(
            f"{case_id}: durable_dispatch reports no governed-loop tool results"
        )
    for field_name, value in (
        ("staleChecks", case.stale_checks),
        ("transientFaults", case.transient_faults),
        ("recoveryPlans", case.recovery_plans),
        ("replanGoals", case.replan_goals),
    ):
        if value:
            raise ValueError(
                f"{case_id}: {field_name} is a governed-loop injection and is not valid "
                "for durable_dispatch cases"
            )
    if case.planned_requests:
        raise ValueError(
            f"{case_id}: durable_dispatch case must not declare governed-loop plans"
        )

    observed = case.dispatch_expected
    if observed.dispatch_error_kind is not None:
        if expected.status != observed.dispatch_error_kind:
            raise ValueError(
                f"{case_id}: a dispatch error case must set status to the error kind"
            )
        if observed.start_status is not None or observed.resume_status is not None:
            raise ValueError(
                f"{case_id}: a dispatch error case must not expect durable start or resume"
            )
    elif expected.status != observed.dispatch_kind:
        raise ValueError(
            f"{case_id}: durable_dispatch status must equal the expected dispatchKind"
        )

    if observed.dispatch_kind == CareerAgentRuntimeDispatchKind.DURABLE_HITL.value:
        if not observed.interrupt_persisted:
            raise ValueError(
                f"{case_id}: a durable_hitl case must observe a persisted interrupt"
            )
        if observed.governed_loop_invocations != 0:
            raise ValueError(
                f"{case_id}: durable_hitl must not invoke the governed loop"
            )
    if observed.dispatch_kind == CareerAgentRuntimeDispatchKind.GOVERNED_LOOP.value:
        if observed.start_status is not None or observed.resume_status is not None:
            raise ValueError(
                f"{case_id}: a governed_loop dispatch must not report durable state"
            )
    if observed.ranking_invocations + observed.gap_invocations != expected.workflow_invocations:
        raise ValueError(
            f"{case_id}: expected.workflowInvocations must equal ranking + gap invocations"
        )
    if observed.provider_calls != 0:
        raise ValueError(f"{case_id}: dispatch eval must observe zero provider calls")


def _validate_governed_loop_case(case: CareerTrajectoryEvalCase) -> None:
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
    if expected.status == "cancelled":
        if expected.error_code is None:
            raise ValueError(f"{case_id}: a cancelled trajectory requires an errorCode")
        if not expected.trace or not expected.trace[-1].startswith("cancelled"):
            raise ValueError(
                f"{case_id}: a cancelled trajectory must end with a cancelled event"
            )
    elif expected.status == "failed":
        if expected.error_code is None:
            raise ValueError(f"{case_id}: a failed trajectory requires an errorCode")
        if not expected.trace or not expected.trace[-1].startswith("failed"):
            raise ValueError(f"{case_id}: a failed trajectory must end with a failed event")
    elif expected.error_code is not None:
        raise ValueError(f"{case_id}: only a failed or cancelled trajectory may declare an errorCode")
    terminal_events = ("failed", "cancelled")
    if expected.status not in ("failed", "cancelled") and expected.trace and any(
        expected.trace[-1].startswith(name) for name in terminal_events
    ):
        raise ValueError(
            f"{case_id}: a non-terminal trajectory must not end with a failed or cancelled event"
        )


def _validate_injection_case(case: CareerTrajectoryEvalCase) -> None:
    case_id = case.case_id
    expected = case.expected

    fault_attempts = sum(
        1 for flags in case.transient_faults.values() for flag in flags if flag
    )
    allowed_invocations = (
        len(case.planned_requests) + len(case.recovery_plans) + fault_attempts
    )
    if expected.workflow_invocations > allowed_invocations:
        raise ValueError(
            f"{case_id}: workflow invocations cannot exceed the declared plans, recovery "
            "plans and injected transient faults"
        )
    for plan in case.planned_requests + case.recovery_plans:
        if plan.request_payload.get("kind") not in _TOOL_REQUEST_REQUEST_TYPE:
            raise ValueError(
                f"{case_id}: planned request for {plan.tool} has an invalid request kind"
            )
    if case.family == "completed_single" and len(case.planned_requests) != 1:
        raise ValueError(f"{case_id}: completed_single requires exactly one planned request")

    goals = case.intent_payload.get("goals")
    if case.family == "tool_empty":
        if goals:
            raise ValueError(f"{case_id}: tool_empty case must declare no intent goals")
        if expected.status != "clarification_required":
            raise ValueError(
                f"{case_id}: tool_empty case must expect clarification_required"
            )

    if case.recovery_plans and case.family != "corrected_retry":
        raise ValueError(
            f"{case_id}: recoveryPlans are only valid for corrected_retry cases"
        )
    if case.family == "corrected_retry" and not case.recovery_plans:
        raise ValueError(f"{case_id}: corrected_retry case requires recoveryPlans")
    if case.replan_goals and case.family != "unknown_tool_replan":
        raise ValueError(
            f"{case_id}: replanGoals are only valid for unknown_tool_replan cases"
        )
    if case.family == "unknown_tool_replan" and not case.replan_goals:
        raise ValueError(f"{case_id}: unknown_tool_replan case requires replanGoals")
    if case.transient_faults and case.family not in ("transient_retry", "stale_terminate"):
        raise ValueError(
            f"{case_id}: transientFaults are only valid for transient_retry or "
            "stale_terminate cases"
        )
    if case.family == "transient_retry" and not case.transient_faults:
        raise ValueError(f"{case_id}: transient_retry case requires transientFaults")
    if case.stale_checks and case.family != "stale_terminate":
        raise ValueError(
            f"{case_id}: staleChecks are only valid for stale_terminate cases"
        )
    if case.family == "stale_terminate":
        if not case.stale_checks:
            raise ValueError(f"{case_id}: stale_terminate case requires staleChecks")
        if expected.error_code != "stale_state":
            raise ValueError(f"{case_id}: stale_terminate case must fail with stale_state")

    recovering_families = ("corrected_retry", "transient_retry", "unknown_tool_replan")
    if case.family in recovering_families and expected.status == "completed":
        if not any(event.startswith("recovery") for event in expected.trace):
            raise ValueError(
                f"{case_id}: a recovered {case.family} trajectory must trace a recovery event"
            )

    if case.clock_script and case.family != "runtime_timeout":
        raise ValueError(
            f"{case_id}: clockScript is only valid for runtime_timeout cases"
        )
    if case.family == "runtime_timeout":
        if not case.clock_script:
            raise ValueError(f"{case_id}: runtime_timeout case requires clockScript")
        if expected.error_code != "runtime_timeout":
            raise ValueError(f"{case_id}: runtime_timeout case must fail with runtime_timeout")
    if case.cancel_after_checks is not None and case.family != "run_cancelled":
        raise ValueError(
            f"{case_id}: cancelAfterChecks is only valid for run_cancelled cases"
        )
    if case.family == "run_cancelled":
        if case.cancel_after_checks is None:
            raise ValueError(f"{case_id}: run_cancelled case requires cancelAfterChecks")
        if expected.status != "cancelled" or expected.error_code != "run_cancelled":
            raise ValueError(
                f"{case_id}: run_cancelled case must end cancelled with run_cancelled"
            )


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


def _parse_plan(
    payload: object,
    *,
    line_number: int,
    index: int,
    field_name: str = "plannedRequests",
) -> CareerTrajectoryEvalPlan:
    plan_payload = _object(payload, field=f"{field_name}[{index}]", line_number=line_number)
    tool = _required_string(plan_payload, "tool", line_number=line_number)
    try:
        CareerAgentToolName(tool)
    except ValueError as exc:
        raise ValueError(
            f"Trajectory Eval line {line_number} {field_name}[{index}] references unknown "
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


def _required_bool(payload: Mapping[str, object], field: str, *, line_number: int) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"Trajectory Eval line {line_number} field {field} must be bool")
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
