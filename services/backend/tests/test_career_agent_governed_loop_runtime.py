"""Minimal governed vNext 1.1 vertical-loop integration tests."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

import pytest

from app.agent.context import CareerAgentContext
from app.agent.execution_gate import CareerAgentGovernedToolExecutor
from app.agent.intent import (
    CareerIntent,
    CareerIntentGoal,
    CareerIntentResolutionContext,
    CareerIntentRouter,
)
from app.agent.tool_loop import CareerAgentLoopBudget
from app.agent.tool_registry import (
    CareerAgentToolName,
    CareerAgentToolRegistry,
    JobPreparationRequest,
    RankMatchReportsRequest,
    TargetCohortGapsRequest,
)
from app.agent.tool_selection import CareerAgentToolSelector
from app.agent.governed_loop_runtime import (
    CareerAgentGovernedLoopRuntime,
    CareerAgentGovernedLoopStatus,
    CareerAgentPlannedToolRequest,
)


class _IntentModel:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def route(self, user_message: str) -> dict[str, object]:
        assert user_message
        return self.payload


class _Workflow:
    def __init__(self, output: object, *, failures: tuple[Exception, ...] = ()) -> None:
        self.output = output
        self.failures = list(failures)
        self.calls: list[object] = []

    def execute(self, *args: object, **kwargs: object) -> object:
        self.calls.append((args, kwargs))
        if self.failures:
            raise self.failures.pop(0)
        return self.output


class _RecoveryPlanner:
    def __init__(self, recovered_plan: CareerAgentPlannedToolRequest) -> None:
        self.recovered_plan = recovered_plan
        self.calls: list[tuple[CareerAgentToolName, str, int]] = []

    def recover_tool_request(
        self,
        *,
        tool: CareerAgentToolName,
        error_code: str,
        previous_plan: CareerAgentPlannedToolRequest | None,
        attempt: int,
    ) -> CareerAgentPlannedToolRequest | None:
        self.calls.append((tool, error_code, attempt))
        return self.recovered_plan


def _fp(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class _StepClock:
    def __init__(self, values: tuple[float, ...]) -> None:
        self.values = list(values)

    def __call__(self) -> float:
        if not self.values:
            raise AssertionError("unexpected clock read")
        return self.values.pop(0)


class _UnknownToolReplanner:
    def __init__(self, goals: tuple[CareerIntentGoal, ...]) -> None:
        self.goals = goals
        self.calls: list[tuple[tuple[CareerIntentGoal, ...], int]] = []

    def replan_unknown_tool(
        self,
        *,
        previous_goals: tuple[CareerIntentGoal, ...],
        attempt: int,
    ) -> tuple[CareerIntentGoal, ...] | None:
        self.calls.append((previous_goals, attempt))
        return self.goals


class _CurrentStalenessGuard:
    def is_stale(
        self,
        *,
        context: CareerAgentContext,
        plan: CareerAgentPlannedToolRequest,
    ) -> bool:
        assert context.usable
        assert plan.fact_fingerprint
        return False


class _StalenessGuard:
    def __init__(self, answers: tuple[bool, ...]) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[CareerAgentToolName, str]] = []

    def is_stale(
        self,
        *,
        context: CareerAgentContext,
        plan: CareerAgentPlannedToolRequest,
    ) -> bool:
        assert context.usable
        self.calls.append((plan.tool, plan.fact_fingerprint))
        if not self.answers:
            raise AssertionError("unexpected stale check")
        return self.answers.pop(0)


def _context() -> CareerAgentContext:
    return CareerAgentContext(
        usable=True,
        confirmation_boundary="confirmed_profile_and_search_intent",
        profile=None,
        search_intent=None,
        current_job=None,
        relevant_evidence=(),
        blockers=(),
        blocker_messages=(),
    )


def _runtime(payload: dict[str, object], *, ranking: _Workflow | None = None):
    ranking = ranking or _Workflow({"jobs": ["job-1"]})
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    return (
        CareerAgentGovernedLoopRuntime(
            router=CareerIntentRouter(model=_IntentModel(payload)),
            selector=CareerAgentToolSelector(registry=registry),
            executor=CareerAgentGovernedToolExecutor(registry=registry),
            staleness_guard=_CurrentStalenessGuard(),
            budget=CareerAgentLoopBudget(max_turns=3, max_tool_calls=3),
        ),
        ranking,
    )


def test_runtime_uses_already_resolved_intent_without_routing_model_again() -> None:
    class _ExplodingIntentModel:
        def route(self, user_message: str) -> dict[str, object]:
            raise AssertionError("resolved intent must not route the model again")

    ranking = _Workflow({"jobs": ["job-1"]})
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_ExplodingIntentModel()),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        staleness_guard=_CurrentStalenessGuard(),
    )
    resolution_context = CareerIntentResolutionContext(run_job_ids=("job-1",))

    result = runtime.run(
        user_message="排序",
        context=_context(),
        resolution_context=resolution_context,
        planned_requests=(
            CareerAgentPlannedToolRequest(
                tool=CareerAgentToolName.RANK_MATCH_REPORTS,
                request=RankMatchReportsRequest(job_ids=("job-1",)),
                normalized_params=(("job_ids", "job-1"),),
                fact_fingerprint=_fp("resolved-intent-facts"),
            ),
        ),
        resolved_intent=CareerIntent(goals=(CareerIntentGoal.RANK_JOBS,)),
    )

    assert result.status is CareerAgentGovernedLoopStatus.COMPLETED
    assert len(ranking.calls) == 1
    assert result.trace[0].event == "intent_routed"


def test_runtime_reports_total_latency_and_completed_terminal_reason() -> None:
    ranking = _Workflow({"jobs": ["job-1"]})
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_IntentModel({"goals": ["rank_jobs"]})),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        staleness_guard=_CurrentStalenessGuard(),
        monotonic_clock=_StepClock((10.0, 10.05, 10.125)),
    )

    result = runtime.run(
        user_message="排序",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(
            CareerAgentPlannedToolRequest(
                tool=CareerAgentToolName.RANK_MATCH_REPORTS,
                request=RankMatchReportsRequest(job_ids=("job-1",)),
                normalized_params=(("job_ids", "job-1"),),
                fact_fingerprint=_fp("latency-success"),
            ),
        ),
    )

    assert result.status is CareerAgentGovernedLoopStatus.COMPLETED
    assert result.runtime_latency_ms == 125.0
    assert result.terminal_reason == "completed"


def test_runtime_stops_before_tool_call_when_runtime_budget_is_exhausted() -> None:
    ranking = _Workflow({"jobs": ["job-1"]})
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_IntentModel({"goals": ["rank_jobs"]})),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        staleness_guard=_CurrentStalenessGuard(),
        budget=CareerAgentLoopBudget(max_runtime_seconds=1),
        monotonic_clock=_StepClock((10.0, 11.1, 11.2)),
    )

    result = runtime.run(
        user_message="排序",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(
            CareerAgentPlannedToolRequest(
                tool=CareerAgentToolName.RANK_MATCH_REPORTS,
                request=RankMatchReportsRequest(job_ids=("job-1",)),
                normalized_params=(("job_ids", "job-1"),),
                fact_fingerprint=_fp("timeout-before-tool"),
            ),
        ),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "runtime_timeout"
    assert result.terminal_reason == "runtime_timeout"
    assert ranking.calls == []
    assert result.trace[-1].event == "failed"
    assert result.trace[-1].error_code == "runtime_timeout"


def test_runtime_does_not_start_transient_retry_after_runtime_budget_expires() -> None:
    ranking = _Workflow(
        {"jobs": ["job-1"]},
        failures=(ConnectionError("temporary ranking backend failure"),),
    )
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_IntentModel({"goals": ["rank_jobs"]})),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        staleness_guard=_CurrentStalenessGuard(),
        budget=CareerAgentLoopBudget(max_turns=3, max_tool_calls=3, max_retries=1, max_runtime_seconds=1),
        monotonic_clock=_StepClock((20.0, 20.1, 21.2, 21.3)),
    )
    plan = CareerAgentPlannedToolRequest(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(job_ids=("job-1",)),
        normalized_params=(("job_ids", "job-1"),),
        fact_fingerprint=_fp("timeout-before-retry"),
    )

    result = runtime.run(
        user_message="排序",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(plan,),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "runtime_timeout"
    assert len(ranking.calls) == 1
    assert tuple(event.event for event in result.trace) == (
        "intent_routed",
        "tool_selected",
        "recovery",
        "failed",
    )


def test_runtime_reports_error_terminal_reason_without_changing_trace_fingerprint() -> None:
    def build(clock: _StepClock) -> tuple[CareerAgentGovernedLoopRuntime, _Workflow]:
        ranking = _Workflow({"jobs": ["job-1"]})
        other = _Workflow({"ok": True})
        registry = CareerAgentToolRegistry(
            ranking=ranking,
            target_cohort_gaps=other,
            job_preparation=other,
        )
        return (
            CareerAgentGovernedLoopRuntime(
                router=CareerIntentRouter(model=_IntentModel({"goals": ["invented_goal"]})),
                selector=CareerAgentToolSelector(registry=registry),
                executor=CareerAgentGovernedToolExecutor(registry=registry),
                staleness_guard=_CurrentStalenessGuard(),
                monotonic_clock=clock,
            ),
            ranking,
        )

    first_runtime, first_ranking = build(_StepClock((20.0, 20.01)))
    second_runtime, second_ranking = build(_StepClock((30.0, 30.25)))
    kwargs = dict(
        user_message="做一个不存在的动作",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(),
    )

    first = first_runtime.run(**kwargs)
    second = second_runtime.run(**kwargs)

    assert first.status is CareerAgentGovernedLoopStatus.FAILED
    assert first.terminal_reason == "invalid_intent_output"
    assert first.runtime_latency_ms != second.runtime_latency_ms
    assert tuple(event.trace_fingerprint for event in first.trace) == tuple(
        event.trace_fingerprint for event in second.trace
    )
    assert first_ranking.calls == []
    assert second_ranking.calls == []


def test_runtime_routes_selects_gates_executes_and_traces_structured_result() -> None:
    runtime, ranking = _runtime({"goals": ["rank_jobs"], "reasoning_summary": "排序。"})

    result = runtime.run(
        user_message="这批岗位先帮我排序",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1", "job-2")),
        planned_requests=(
            CareerAgentPlannedToolRequest(
                tool=CareerAgentToolName.RANK_MATCH_REPORTS,
                request=RankMatchReportsRequest(job_ids=("job-1", "job-2")),
                normalized_params=(("job_ids", "job-1,job-2"),),
                fact_fingerprint=_fp("facts-1"),
            ),
        ),
    )

    assert result.status is CareerAgentGovernedLoopStatus.COMPLETED
    assert len(ranking.calls) == 1
    assert len(result.tool_results) == 1
    assert result.tool_results[0].status.value == "success"
    assert result.tool_results[0].result_fingerprint
    assert tuple(event.event for event in result.trace) == (
        "intent_routed",
        "tool_selected",
        "tool_called",
        "tool_result",
        "finished",
    )
    assert all(event.trace_fingerprint for event in result.trace)


def test_runtime_requires_clarification_when_intent_selects_no_tool() -> None:
    runtime, ranking = _runtime({"goals": [], "reasoning_summary": "No workflow is necessary yet."})

    result = runtime.run(
        user_message="先看看情况",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(),
    )

    assert result.status is CareerAgentGovernedLoopStatus.CLARIFICATION_REQUIRED
    assert result.message == "No executable Career Agent tool was selected. Please clarify the next action."
    assert ranking.calls == []
    assert tuple(event.event for event in result.trace) == ("intent_routed", "clarification")


def test_runtime_returns_clarification_without_tool_execution() -> None:
    runtime, ranking = _runtime(
        {
            "goals": [],
            "needs_clarification": True,
            "clarification_question": "请明确岗位。",
        }
    )

    result = runtime.run(
        user_message="这个怎么样",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(),
        planned_requests=(),
    )

    assert result.status is CareerAgentGovernedLoopStatus.CLARIFICATION_REQUIRED
    assert result.message == "请明确岗位。"
    assert ranking.calls == []
    assert tuple(event.event for event in result.trace) == ("intent_routed", "clarification")


def test_runtime_returns_structured_failure_when_planned_requests_are_duplicated() -> None:
    runtime, ranking = _runtime({"goals": ["rank_jobs"]})
    duplicated_plan = CareerAgentPlannedToolRequest(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(job_ids=("job-1",)),
        normalized_params=(("job_ids", "job-1"),),
        fact_fingerprint=_fp("facts-1"),
    )

    result = runtime.run(
        user_message="排序",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(duplicated_plan, duplicated_plan),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "invalid_tool_params"
    assert ranking.calls == []
    assert result.trace[-1].event == "failed"


def test_runtime_returns_structured_failure_when_turn_budget_is_exhausted() -> None:
    ranking = _Workflow({"jobs": ["job-1"]})
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(
            model=_IntentModel(
                {
                    "goals": ["rank_jobs", "review_gaps"],
                    "reasoning_summary": "先排序，再看差距。",
                }
            )
        ),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        staleness_guard=_CurrentStalenessGuard(),
        budget=CareerAgentLoopBudget(max_turns=1, max_tool_calls=2),
    )

    result = runtime.run(
        user_message="先排序再看差距",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(
            CareerAgentPlannedToolRequest(
                tool=CareerAgentToolName.RANK_MATCH_REPORTS,
                request=RankMatchReportsRequest(job_ids=("job-1",)),
                normalized_params=(("job_ids", "job-1"),),
                fact_fingerprint=_fp("facts-rank"),
            ),
            CareerAgentPlannedToolRequest(
                tool=CareerAgentToolName.TARGET_COHORT_GAPS,
                request=TargetCohortGapsRequest(
                    cohort_id="cohort-1",
                    name="target",
                    selected_job_ids=("job-1",),
                ),
                normalized_params=(("selected_job_ids", "job-1"),),
                fact_fingerprint=_fp("facts-gap"),
            ),
        ),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "budget_exhausted"
    assert len(ranking.calls) == 1
    assert result.trace[-1].event == "failed"
    assert result.trace[-1].tool is CareerAgentToolName.TARGET_COHORT_GAPS


def test_runtime_returns_structured_failure_for_malformed_intent_output() -> None:
    runtime, ranking = _runtime({"goals": ["invented_goal"]})

    result = runtime.run(
        user_message="做一个不存在的动作",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "invalid_intent_output"
    assert ranking.calls == []
    assert tuple(event.event for event in result.trace) == ("failed",)


def test_runtime_replans_invalid_tool_params_once_with_corrected_request() -> None:
    invalid_plan = CareerAgentPlannedToolRequest(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(job_ids=()),
        normalized_params=(("job_ids", ""),),
        fact_fingerprint=_fp("facts-invalid"),
    )
    recovered_plan = CareerAgentPlannedToolRequest(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(job_ids=("job-1",)),
        normalized_params=(("job_ids", "job-1"),),
        fact_fingerprint=_fp("facts-corrected"),
    )
    recovery = _RecoveryPlanner(recovered_plan)
    ranking = _Workflow({"jobs": ["job-1"]})
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_IntentModel({"goals": ["rank_jobs"]})),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        staleness_guard=_CurrentStalenessGuard(),
        budget=CareerAgentLoopBudget(max_turns=3, max_tool_calls=3),
        recovery_planner=recovery,
    )

    result = runtime.run(
        user_message="排序",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(invalid_plan,),
    )

    assert result.status is CareerAgentGovernedLoopStatus.COMPLETED
    assert len(ranking.calls) == 1
    assert recovery.calls == [(CareerAgentToolName.RANK_MATCH_REPORTS, "invalid_tool_params", 1)]
    assert tuple(event.event for event in result.trace) == (
        "intent_routed",
        "tool_selected",
        "recovery",
        "tool_called",
        "tool_result",
        "finished",
    )
    assert result.trace[2].error_code == "invalid_tool_params"


def test_runtime_retries_transient_tool_error_once_with_same_grounded_request() -> None:
    ranking = _Workflow(
        {"jobs": ["job-1"]},
        failures=(ConnectionError("temporary ranking backend failure"),),
    )
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_IntentModel({"goals": ["rank_jobs"]})),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        staleness_guard=_CurrentStalenessGuard(),
        budget=CareerAgentLoopBudget(max_turns=3, max_tool_calls=3, max_retries=1),
    )
    plan = CareerAgentPlannedToolRequest(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(job_ids=("job-1",)),
        normalized_params=(("job_ids", "job-1"),),
        fact_fingerprint=_fp("facts-rank"),
    )

    result = runtime.run(
        user_message="排序",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(plan,),
    )

    assert result.status is CareerAgentGovernedLoopStatus.COMPLETED
    assert len(ranking.calls) == 2
    assert tuple(event.event for event in result.trace) == (
        "intent_routed",
        "tool_selected",
        "recovery",
        "tool_called",
        "tool_result",
        "finished",
    )
    assert result.trace[2].error_code == "transient_network"


def test_runtime_replans_unknown_tool_once_into_registered_goal() -> None:
    ranking = _Workflow({"jobs": ["job-1"]})
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    replanner = _UnknownToolReplanner((CareerIntentGoal.RANK_JOBS,))
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_IntentModel({"goals": ["unknown"]})),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        staleness_guard=_CurrentStalenessGuard(),
        budget=CareerAgentLoopBudget(max_turns=3, max_tool_calls=3, max_retries=1),
        unknown_tool_replanner=replanner,
    )
    plan = CareerAgentPlannedToolRequest(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(job_ids=("job-1",)),
        normalized_params=(("job_ids", "job-1"),),
        fact_fingerprint=_fp("facts-rank"),
    )

    result = runtime.run(
        user_message="帮我处理一下这批岗位",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(plan,),
    )

    assert result.status is CareerAgentGovernedLoopStatus.COMPLETED
    assert len(ranking.calls) == 1
    assert replanner.calls == [((CareerIntentGoal.UNKNOWN,), 1)]
    assert tuple(event.event for event in result.trace) == (
        "intent_routed",
        "recovery",
        "tool_selected",
        "tool_called",
        "tool_result",
        "finished",
    )
    assert result.trace[1].error_code == "unknown_tool"


def test_runtime_fails_closed_when_unknown_tool_replan_is_still_unknown() -> None:
    ranking = _Workflow({"jobs": ["job-1"]})
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    replanner = _UnknownToolReplanner((CareerIntentGoal.UNKNOWN,))
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_IntentModel({"goals": ["unknown"]})),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        staleness_guard=_CurrentStalenessGuard(),
        budget=CareerAgentLoopBudget(max_turns=3, max_tool_calls=3, max_retries=1),
        unknown_tool_replanner=replanner,
    )

    result = runtime.run(
        user_message="调用一个不存在的工具",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "unknown_tool"
    assert ranking.calls == []
    assert replanner.calls == [((CareerIntentGoal.UNKNOWN,), 1)]
    assert tuple(event.event for event in result.trace) == (
        "intent_routed",
        "recovery",
        "failed",
    )
    assert result.trace[-1].error_code == "unknown_tool"


def test_runtime_keeps_unavailable_future_goal_fail_closed_without_unknown_replan() -> None:
    ranking = _Workflow({"jobs": ["job-1"]})
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    replanner = _UnknownToolReplanner((CareerIntentGoal.RANK_JOBS,))
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_IntentModel({"goals": ["review_application"]})),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        staleness_guard=_CurrentStalenessGuard(),
        unknown_tool_replanner=replanner,
    )

    result = runtime.run(
        user_message="查看申请执行情况",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "invalid_tool_params"
    assert ranking.calls == []
    assert replanner.calls == []


def test_planned_request_rejects_non_digest_fact_fingerprint() -> None:
    with pytest.raises(ValueError, match="64-character lowercase sha256"):
        CareerAgentPlannedToolRequest(
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            request=RankMatchReportsRequest(job_ids=("job-1",)),
            normalized_params=(("job_ids", "job-1"),),
            fact_fingerprint="raw job facts must never enter trace",
        )


def test_runtime_terminates_stale_plan_before_workflow_execution() -> None:
    ranking = _Workflow({"jobs": ["job-1"]})
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    stale = _StalenessGuard((True,))
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_IntentModel({"goals": ["rank_jobs"]})),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        staleness_guard=stale,
    )
    plan = CareerAgentPlannedToolRequest(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(job_ids=("job-1",)),
        normalized_params=(("job_ids", "job-1"),),
        fact_fingerprint=_fp("stale-ranking-facts"),
    )

    result = runtime.run(
        user_message="重新看这批岗位",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(plan,),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "stale_state"
    assert ranking.calls == []
    assert stale.calls == [(CareerAgentToolName.RANK_MATCH_REPORTS, plan.fact_fingerprint)]
    assert tuple(event.event for event in result.trace) == (
        "intent_routed",
        "tool_selected",
        "failed",
    )
    assert result.trace[-1].tool is CareerAgentToolName.RANK_MATCH_REPORTS
    assert result.trace[-1].input_fingerprint == plan.fact_fingerprint


def test_runtime_rechecks_staleness_before_transient_retry() -> None:
    ranking = _Workflow(
        {"jobs": ["job-1"]},
        failures=(ConnectionError("temporary ranking backend failure"),),
    )
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    stale = _StalenessGuard((False, True))
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_IntentModel({"goals": ["rank_jobs"]})),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        budget=CareerAgentLoopBudget(max_turns=3, max_tool_calls=3, max_retries=1),
        staleness_guard=stale,
    )
    plan = CareerAgentPlannedToolRequest(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(job_ids=("job-1",)),
        normalized_params=(("job_ids", "job-1"),),
        fact_fingerprint=_fp("retry-ranking-facts"),
    )

    result = runtime.run(
        user_message="排序",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(plan,),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "stale_state"
    assert len(ranking.calls) == 1
    assert len(stale.calls) == 2
    assert tuple(event.event for event in result.trace) == (
        "intent_routed",
        "tool_selected",
        "recovery",
        "failed",
    )


def test_runtime_rechecks_staleness_after_corrected_replan() -> None:
    invalid_plan = CareerAgentPlannedToolRequest(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(job_ids=()),
        normalized_params=(("job_ids", ""),),
        fact_fingerprint=_fp("invalid-stale-facts"),
    )
    recovered_plan = CareerAgentPlannedToolRequest(
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(job_ids=("job-1",)),
        normalized_params=(("job_ids", "job-1"),),
        fact_fingerprint=_fp("corrected-but-stale-facts"),
    )
    recovery = _RecoveryPlanner(recovered_plan)
    ranking = _Workflow({"jobs": ["job-1"]})
    other = _Workflow({"ok": True})
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    stale = _StalenessGuard((False, True))
    runtime = CareerAgentGovernedLoopRuntime(
        router=CareerIntentRouter(model=_IntentModel({"goals": ["rank_jobs"]})),
        selector=CareerAgentToolSelector(registry=registry),
        executor=CareerAgentGovernedToolExecutor(registry=registry),
        recovery_planner=recovery,
        staleness_guard=stale,
    )

    result = runtime.run(
        user_message="排序",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(invalid_plan,),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "stale_state"
    assert ranking.calls == []
    assert recovery.calls == [(CareerAgentToolName.RANK_MATCH_REPORTS, "invalid_tool_params", 1)]
    assert stale.calls[-1] == (
        CareerAgentToolName.RANK_MATCH_REPORTS,
        recovered_plan.fact_fingerprint,
    )
    assert tuple(event.event for event in result.trace) == (
        "intent_routed",
        "tool_selected",
        "recovery",
        "failed",
    )


def test_runtime_fails_closed_when_selected_tool_has_no_exact_planned_request() -> None:
    runtime, ranking = _runtime({"goals": ["rank_jobs"]})

    result = runtime.run(
        user_message="排序",
        context=_context(),
        resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        planned_requests=(
            CareerAgentPlannedToolRequest(
                tool=CareerAgentToolName.JOB_PREPARATION,
                request=JobPreparationRequest(job_id="job-1"),
                normalized_params=(("job_id", "job-1"),),
                fact_fingerprint=_fp("facts-1"),
            ),
        ),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "invalid_tool_params"
    assert ranking.calls == []
    assert result.trace[-1].event == "failed"
