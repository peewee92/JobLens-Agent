from dataclasses import dataclass

import pytest

from app.agent.context import CareerAgentContext, CareerAgentJobContext
from app.agent.entrypoint import (
    CareerAgentEntrypoint,
    CareerAgentEntrypointError,
    CareerAgentGoal,
    CareerAgentTurn,
)
from app.agent.tool_registry import CareerAgentToolName


@dataclass
class _Builder:
    context: CareerAgentContext

    def build(self, **_: object) -> CareerAgentContext:
        return self.context


class _Tools:
    def __init__(self) -> None:
        self.calls: list[tuple[CareerAgentToolName, object]] = []

    def invoke(self, *, context: CareerAgentContext, tool: CareerAgentToolName, request: object) -> object:
        assert context.usable
        self.calls.append((tool, request))
        return {"tool": tool.value}


def _context(*, usable: bool = True, job_id: str | None = None) -> CareerAgentContext:
    current_job = None
    if job_id is not None:
        current_job = CareerAgentJobContext(id=job_id, title="Role", company="Acme", area=None)
    return CareerAgentContext(
        usable=usable,
        confirmation_boundary="confirmed",
        profile=None,
        search_intent=None,
        current_job=current_job,
        relevant_evidence=(),
        blockers=(),
        blocker_messages=(),
    )


def test_entrypoint_routes_ranking_through_registry() -> None:
    tools = _Tools()
    entrypoint = CareerAgentEntrypoint(context_builder=_Builder(_context()), tools=tools)

    result = entrypoint.execute(
        CareerAgentTurn(goal=CareerAgentGoal.RANK_JOBS, job_ids=("job-1", "job-2"), top_n=2)
    )

    assert result.tool is CareerAgentToolName.RANK_MATCH_REPORTS
    assert result.output == {"tool": "rank_match_reports"}
    assert len(tools.calls) == 1


def test_entrypoint_stops_before_tools_when_context_is_not_usable() -> None:
    tools = _Tools()
    entrypoint = CareerAgentEntrypoint(context_builder=_Builder(_context(usable=False)), tools=tools)

    result = entrypoint.execute(CareerAgentTurn(goal=CareerAgentGoal.RANK_JOBS, job_ids=("job-1",)))

    assert result.tool is None
    assert result.output is None
    assert tools.calls == []


def test_entrypoint_requires_explicit_feedback_for_gap_review() -> None:
    entrypoint = CareerAgentEntrypoint(context_builder=_Builder(_context()), tools=_Tools())

    with pytest.raises(CareerAgentEntrypointError, match="selected_feedback_ids"):
        entrypoint.execute(
            CareerAgentTurn(
                goal=CareerAgentGoal.REVIEW_GAPS,
                cohort_id="cohort-1",
                cohort_name="Target",
            )
        )


def test_entrypoint_locks_prepare_to_governed_current_job() -> None:
    tools = _Tools()
    entrypoint = CareerAgentEntrypoint(
        context_builder=_Builder(_context(job_id="job-1")),
        tools=tools,
    )

    result = entrypoint.execute(
        CareerAgentTurn(goal=CareerAgentGoal.PREPARE_JOB, current_job_id="job-1")
    )

    assert result.tool is CareerAgentToolName.JOB_PREPARATION
    assert len(tools.calls) == 1


def test_entrypoint_rejects_ranking_without_explicit_jobs() -> None:
    entrypoint = CareerAgentEntrypoint(context_builder=_Builder(_context()), tools=_Tools())

    with pytest.raises(CareerAgentEntrypointError, match="job_ids"):
        entrypoint.execute(CareerAgentTurn(goal=CareerAgentGoal.RANK_JOBS))
