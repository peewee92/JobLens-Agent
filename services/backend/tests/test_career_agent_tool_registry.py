"""Governed Career Agent workflow registry tests."""
from __future__ import annotations

import pytest

from app.agent.context import CareerAgentContext, CareerAgentJobContext
from app.agent.tool_registry import (
    CareerAgentToolAccess,
    CareerAgentToolError,
    CareerAgentToolName,
    CareerAgentToolRegistry,
    JobPreparationRequest,
    RankMatchReportsRequest,
    TargetCohortGapsRequest,
)


class FakeRankingWorkflow:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], bool, int | None]] = []

    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        include_blocked: bool = False,
        top_n: int | None = None,
    ) -> object:
        self.calls.append((job_ids, include_blocked, top_n))
        return {"ranked": job_ids}


class FakeGapWorkflow:
    def __init__(self) -> None:
        self.commands: list[object] = []

    def execute(self, command: object) -> object:
        self.commands.append(command)
        return {"gap": "facts"}


class FakePreparationWorkflow:
    def __init__(self) -> None:
        self.job_ids: list[str] = []

    def execute(self, job_id: str) -> object:
        self.job_ids.append(job_id)
        return {"prepared": job_id}


def _context(*, usable: bool = True, current_job_id: str | None = None) -> CareerAgentContext:
    current_job = (
        CareerAgentJobContext(
            id=current_job_id,
            title="AI Application Engineer",
            company="Example AI",
            area="武汉",
        )
        if current_job_id is not None
        else None
    )
    return CareerAgentContext(
        usable=usable,
        confirmation_boundary="confirmed_profile_and_search_intent",
        profile=None,
        search_intent=None,
        current_job=current_job,
        relevant_evidence=(),
        blockers=(),
        blocker_messages=(),
    )


def _registry() -> tuple[
    CareerAgentToolRegistry,
    FakeRankingWorkflow,
    FakeGapWorkflow,
    FakePreparationWorkflow,
]:
    ranking = FakeRankingWorkflow()
    gaps = FakeGapWorkflow()
    preparation = FakePreparationWorkflow()
    return (
        CareerAgentToolRegistry(
            ranking=ranking,
            target_cohort_gaps=gaps,
            job_preparation=preparation,
        ),
        ranking,
        gaps,
        preparation,
    )


def test_registry_only_exposes_mature_read_only_workflows() -> None:
    registry, _, _, _ = _registry()

    definitions = registry.definitions()

    assert tuple(item.name for item in definitions) == (
        CareerAgentToolName.RANK_MATCH_REPORTS,
        CareerAgentToolName.TARGET_COHORT_GAPS,
        CareerAgentToolName.JOB_PREPARATION,
    )
    assert all(item.access is CareerAgentToolAccess.READ_ONLY for item in definitions)
    exposed_names = {item.name.value for item in definitions}
    assert "create_user_feedback" not in exposed_names
    assert "extract_job_requirements" not in exposed_names
    assert "execute_match" not in exposed_names


def test_ranking_delegates_to_existing_workflow_with_explicit_job_ids() -> None:
    registry, ranking, _, _ = _registry()

    result = registry.invoke(
        context=_context(),
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(
            job_ids=("job_2", "job_1", "job_2"),
            include_blocked=True,
            top_n=2,
        ),
    )

    assert result == {"ranked": ("job_2", "job_1")}
    assert ranking.calls == [(('job_2', 'job_1'), True, 2)]


def test_gap_tool_requires_explicit_feedback_selection_and_preserves_it() -> None:
    registry, _, gaps, _ = _registry()

    with pytest.raises(CareerAgentToolError, match="explicit current UserFeedback"):
        registry.invoke(
            context=_context(),
            tool=CareerAgentToolName.TARGET_COHORT_GAPS,
            request=TargetCohortGapsRequest(
                cohort_id="cohort_1",
                name="Agent target cohort",
                selected_feedback_ids=(),
            ),
        )

    registry.invoke(
        context=_context(),
        tool=CareerAgentToolName.TARGET_COHORT_GAPS,
        request=TargetCohortGapsRequest(
            cohort_id="cohort_1",
            name="Agent target cohort",
            selected_feedback_ids=("feedback_2", "feedback_1", "feedback_2"),
        ),
    )

    command = gaps.commands[0]
    assert command.selected_feedback_ids == ("feedback_2", "feedback_1")  # type: ignore[attr-defined]


def test_gap_tool_accepts_explicit_human_confirmed_job_selection() -> None:
    registry, _, gaps, _ = _registry()

    registry.invoke(
        context=_context(),
        tool=CareerAgentToolName.TARGET_COHORT_GAPS,
        request=TargetCohortGapsRequest(
            cohort_id="cohort_agent_run",
            name="Confirmed target cohort",
            selected_job_ids=("job_3", "job_1", "job_3"),
        ),
    )

    command = gaps.commands[0]
    assert command.selected_job_ids == ("job_3", "job_1")  # type: ignore[attr-defined]


def test_preparation_is_pinned_to_governed_current_job() -> None:
    registry, _, _, preparation = _registry()

    result = registry.invoke(
        context=_context(current_job_id="job_1"),
        tool=CareerAgentToolName.JOB_PREPARATION,
        request=JobPreparationRequest(),
    )

    assert result == {"prepared": "job_1"}
    assert preparation.job_ids == ["job_1"]

    with pytest.raises(CareerAgentToolError, match="cannot switch away"):
        registry.invoke(
            context=_context(current_job_id="job_1"),
            tool=CareerAgentToolName.JOB_PREPARATION,
            request=JobPreparationRequest(job_id="job_2"),
        )


def test_unusable_context_blocks_every_workflow_before_delegation() -> None:
    registry, ranking, gaps, preparation = _registry()

    with pytest.raises(CareerAgentToolError, match="context must be usable"):
        registry.invoke(
            context=_context(usable=False),
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            request=RankMatchReportsRequest(job_ids=("job_1",)),
        )

    assert ranking.calls == []
    assert gaps.commands == []
    assert preparation.job_ids == []
