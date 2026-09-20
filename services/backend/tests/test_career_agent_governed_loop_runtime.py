"""Minimal governed vNext 1.1 vertical-loop integration tests."""
from __future__ import annotations

from dataclasses import dataclass

from app.agent.context import CareerAgentContext
from app.agent.execution_gate import CareerAgentGovernedToolExecutor
from app.agent.intent import CareerIntentResolutionContext, CareerIntentRouter
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
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[object] = []

    def execute(self, *args: object, **kwargs: object) -> object:
        self.calls.append((args, kwargs))
        return self.output


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
            budget=CareerAgentLoopBudget(max_turns=3, max_tool_calls=3),
        ),
        ranking,
    )


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
                fact_fingerprint="facts-1",
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
        fact_fingerprint="facts-1",
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
                fact_fingerprint="facts-rank",
            ),
            CareerAgentPlannedToolRequest(
                tool=CareerAgentToolName.TARGET_COHORT_GAPS,
                request=TargetCohortGapsRequest(
                    cohort_id="cohort-1",
                    name="target",
                    selected_job_ids=("job-1",),
                ),
                normalized_params=(("selected_job_ids", "job-1"),),
                fact_fingerprint="facts-gap",
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
                fact_fingerprint="facts-1",
            ),
        ),
    )

    assert result.status is CareerAgentGovernedLoopStatus.FAILED
    assert result.error_code == "invalid_tool_params"
    assert ranking.calls == []
    assert result.trace[-1].event == "failed"
