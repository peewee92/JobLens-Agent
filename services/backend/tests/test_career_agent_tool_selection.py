"""Governed vNext 1.1 tool-selection boundary tests."""
from __future__ import annotations

import pytest

from app.agent.intent import CareerIntent, CareerIntentGoal
from app.agent.tool_registry import (
    CareerAgentHumanGateRequirement,
    CareerAgentProviderCostClass,
    CareerAgentSideEffectClass,
    CareerAgentToolError,
    CareerAgentToolName,
    CareerAgentToolRegistry,
    JobPreparationRequest,
)
from app.agent.tool_selection import CareerAgentToolSelector, CareerAgentToolSelectionError


class _UnusedWorkflow:
    def execute(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("tool selection must not execute workflows")


def _registry() -> CareerAgentToolRegistry:
    unused = _UnusedWorkflow()
    return CareerAgentToolRegistry(
        ranking=unused,  # type: ignore[arg-type]
        target_cohort_gaps=unused,  # type: ignore[arg-type]
        job_preparation=unused,  # type: ignore[arg-type]
    )


def test_registry_exposes_complete_execution_policy_for_every_tool() -> None:
    definitions = _registry().definitions()

    assert definitions
    assert all(item.input_schema is not None for item in definitions)
    assert all(item.output_schema for item in definitions)
    assert all(item.side_effect_class is CareerAgentSideEffectClass.READ_ONLY for item in definitions)
    assert all(item.provider_cost_class is CareerAgentProviderCostClass.NONE for item in definitions)
    assert all(
        item.human_gate_requirement is CareerAgentHumanGateRequirement.NONE
        for item in definitions
    )


def test_selector_preserves_multi_goal_order_without_executing_tools() -> None:
    selector = CareerAgentToolSelector(registry=_registry())

    selections = selector.select(
        CareerIntent(
            goals=(
                CareerIntentGoal.RANK_JOBS,
                CareerIntentGoal.REVIEW_GAPS,
                CareerIntentGoal.PREPARE_JOB,
            ),
            reasoning_summary="先排序，再看差距，最后准备岗位。",
        )
    )

    assert tuple(item.goal for item in selections) == (
        CareerIntentGoal.RANK_JOBS,
        CareerIntentGoal.REVIEW_GAPS,
        CareerIntentGoal.PREPARE_JOB,
    )
    assert tuple(item.tool.name for item in selections) == (
        CareerAgentToolName.RANK_MATCH_REPORTS,
        CareerAgentToolName.TARGET_COHORT_GAPS,
        CareerAgentToolName.JOB_PREPARATION,
    )


def test_selector_stops_before_tools_for_clarification_or_unsupported_intent() -> None:
    selector = CareerAgentToolSelector(registry=_registry())

    assert selector.select(
        CareerIntent(
            needs_clarification=True,
            clarification_question="请明确岗位。",
        )
    ) == ()
    assert selector.select(
        CareerIntent(unsupported_request="automated_job_application")
    ) == ()


def test_unregistered_intent_goal_fails_closed() -> None:
    selector = CareerAgentToolSelector(registry=_registry())

    with pytest.raises(CareerAgentToolSelectionError, match="no registered tool"):
        selector.select(CareerIntent(goals=(CareerIntentGoal.REVIEW_APPLICATION,)))


def test_registry_rejects_unknown_tool_name_before_workflow_execution() -> None:
    registry = _registry()

    with pytest.raises(CareerAgentToolError, match="unknown Career Agent tool"):
        registry.definition("send_recruiter_message")


def test_registry_rejects_invalid_request_type_before_workflow_execution() -> None:
    registry = _registry()

    with pytest.raises(CareerAgentToolError, match="requires RankMatchReportsRequest"):
        registry.invoke(
            context=_usable_context(),
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            request=JobPreparationRequest(job_id="job-1"),
        )


def _usable_context():
    from app.agent.context import CareerAgentContext

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
