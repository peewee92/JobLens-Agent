from dataclasses import dataclass

from app.agent.context import CareerAgentContext
from app.agent.entrypoint import CareerAgentGoal, CareerAgentTurn, CareerAgentTurnResult
from app.agent.runtimes.base import CareerAgentRuntime
from app.agent.runtimes.workflow_runtime import WorkflowCareerAgentRuntime
from app.agent.tool_registry import CareerAgentToolName


@dataclass
class _Entrypoint:
    calls: list[CareerAgentTurn]

    def execute(self, turn: CareerAgentTurn) -> CareerAgentTurnResult:
        self.calls.append(turn)
        return CareerAgentTurnResult(
            context=CareerAgentContext(
                usable=True,
                confirmation_boundary="confirmed",
                profile=None,
                search_intent=None,
                current_job=None,
                relevant_evidence=(),
                blockers=(),
                blocker_messages=(),
            ),
            goal=turn.goal,
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            output={"items": [{"jobId": "job-1"}]},
        )


def _accepts_runtime(runtime: CareerAgentRuntime) -> CareerAgentRuntime:
    return runtime


def test_workflow_runtime_delegates_without_changing_single_turn_behavior() -> None:
    entrypoint = _Entrypoint(calls=[])
    runtime = _accepts_runtime(WorkflowCareerAgentRuntime(entrypoint=entrypoint))
    turn = CareerAgentTurn(
        goal=CareerAgentGoal.RANK_JOBS,
        job_ids=("job-1",),
        top_n=1,
    )

    result = runtime.run(turn)

    assert entrypoint.calls == [turn]
    assert result.goal is CareerAgentGoal.RANK_JOBS
    assert result.tool is CareerAgentToolName.RANK_MATCH_REPORTS
    assert result.output == {"items": [{"jobId": "job-1"}]}
