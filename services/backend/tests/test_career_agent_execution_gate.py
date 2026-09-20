from dataclasses import replace

import pytest

from app.agent.context import CareerAgentContext
from app.agent.execution_gate import (
    CareerAgentExecutionGate,
    CareerAgentExecutionGateError,
    CareerAgentExecutionGateOutcome,
    CareerAgentGovernedToolExecutor,
)
from app.agent.tool_registry import (
    CareerAgentHumanGateRequirement,
    CareerAgentProviderCostClass,
    CareerAgentSideEffectClass,
    CareerAgentToolDefinition,
    CareerAgentToolName,
    CareerAgentToolRegistry,
    RankMatchReportsRequest,
)


class _Workflow:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"ok": True}


def _registry() -> CareerAgentToolRegistry:
    workflow = _Workflow()
    return CareerAgentToolRegistry(
        ranking=workflow,
        target_cohort_gaps=workflow,
        job_preparation=workflow,
    )


def _definition(**changes: object) -> CareerAgentToolDefinition:
    base = _registry().definition(CareerAgentToolName.RANK_MATCH_REPORTS)
    return replace(base, **changes)


def test_read_only_zero_cost_tool_is_allowed_without_pending_action() -> None:
    decision = CareerAgentExecutionGate().evaluate(
        definition=_definition(),
        normalized_params=(("job_ids", "job-1,job-2"),),
        fact_fingerprint="facts-v1",
    )

    assert decision.outcome is CareerAgentExecutionGateOutcome.ALLOW
    assert decision.pending_action is None


def test_provider_compute_requires_pending_action_with_bounded_cost_metadata() -> None:
    decision = CareerAgentExecutionGate().evaluate(
        definition=_definition(
            side_effect_class=CareerAgentSideEffectClass.PROVIDER_COMPUTE,
            provider_cost_class=CareerAgentProviderCostClass.BOUNDED,
            human_gate_requirement=CareerAgentHumanGateRequirement.COST_APPROVAL,
        ),
        normalized_params=(("job_id", "job-1"),),
        fact_fingerprint="facts-v2",
        expected_provider_calls=1,
        expires_at="2026-09-20T01:00:00Z",
    )

    assert decision.outcome is CareerAgentExecutionGateOutcome.PENDING_ACTION
    assert decision.pending_action is not None
    assert decision.pending_action.tool is CareerAgentToolName.RANK_MATCH_REPORTS
    assert decision.pending_action.cost_class is CareerAgentProviderCostClass.BOUNDED
    assert decision.pending_action.expected_provider_calls == 1
    assert decision.pending_action.business_writes == 0
    assert decision.pending_action.external_effects == ()
    assert decision.pending_action.fact_fingerprint == "facts-v2"
    assert decision.pending_action.action_fingerprint


def test_business_write_and_external_action_never_auto_execute() -> None:
    gate = CareerAgentExecutionGate()

    write = gate.evaluate(
        definition=_definition(side_effect_class=CareerAgentSideEffectClass.BUSINESS_WRITE),
        normalized_params=(("feedback_id", "feedback-1"),),
        fact_fingerprint="facts-write",
        business_writes=1,
        expires_at="2026-09-20T01:00:00Z",
    )
    external = gate.evaluate(
        definition=_definition(side_effect_class=CareerAgentSideEffectClass.EXTERNAL_ACTION),
        normalized_params=(("job_id", "job-1"),),
        fact_fingerprint="facts-external",
        external_effects=("submit_application",),
        expires_at="2026-09-20T01:00:00Z",
    )

    assert write.outcome is CareerAgentExecutionGateOutcome.PENDING_ACTION
    assert write.pending_action is not None
    assert write.pending_action.business_writes == 1
    assert external.outcome is CareerAgentExecutionGateOutcome.PENDING_ACTION
    assert external.pending_action is not None
    assert external.pending_action.external_effects == ("submit_application",)


def test_explicit_human_gate_blocks_even_transient_compute() -> None:
    decision = CareerAgentExecutionGate().evaluate(
        definition=_definition(
            side_effect_class=CareerAgentSideEffectClass.TRANSIENT_COMPUTE,
            human_gate_requirement=CareerAgentHumanGateRequirement.EXPLICIT_APPROVAL,
        ),
        normalized_params=(("job_id", "job-1"),),
        fact_fingerprint="facts-v3",
        expires_at="2026-09-20T01:00:00Z",
    )

    assert decision.outcome is CareerAgentExecutionGateOutcome.PENDING_ACTION


def test_pending_action_is_deterministic_and_does_not_accept_unbounded_params() -> None:
    gate = CareerAgentExecutionGate()
    definition = _definition(side_effect_class=CareerAgentSideEffectClass.BUSINESS_WRITE)
    kwargs = dict(
        definition=definition,
        normalized_params=(("job_id", "job-1"), ("action", "save")),
        fact_fingerprint="facts-v4",
        business_writes=1,
        expires_at="2026-09-20T01:00:00Z",
    )

    first = gate.evaluate(**kwargs)
    second = gate.evaluate(**kwargs)

    assert first.pending_action == second.pending_action
    assert first.pending_action is not None
    assert len(first.pending_action.normalized_params) == 2

    with pytest.raises(CareerAgentExecutionGateError, match="bounded"):
        gate.evaluate(
            definition=definition,
            normalized_params=tuple((f"key-{index}", "value") for index in range(33)),
            fact_fingerprint="facts-v4",
            business_writes=1,
            expires_at="2026-09-20T01:00:00Z",
        )


def test_governed_executor_invokes_registry_only_after_allow_decision() -> None:
    ranking = _Workflow()
    other = _Workflow()
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=other,
        job_preparation=other,
    )
    executor = CareerAgentGovernedToolExecutor(registry=registry)
    context = CareerAgentContext(
        usable=True,
        confirmation_boundary="confirmed_profile_and_search_intent",
        profile=None,
        search_intent=None,
        current_job=None,
        relevant_evidence=(),
        blockers=(),
        blocker_messages=(),
    )

    result = executor.execute(
        context=context,
        tool=CareerAgentToolName.RANK_MATCH_REPORTS,
        request=RankMatchReportsRequest(job_ids=("job-1", "job-2")),
        normalized_params=(("job_ids", "job-1,job-2"),),
        fact_fingerprint="facts-runtime",
    )

    assert result.gate.outcome is CareerAgentExecutionGateOutcome.ALLOW
    assert result.output == {"ok": True}
    assert len(ranking.calls) == 1


def test_inconsistent_effect_metadata_fails_closed() -> None:
    gate = CareerAgentExecutionGate()

    with pytest.raises(CareerAgentExecutionGateError, match="provider"):
        gate.evaluate(
            definition=_definition(side_effect_class=CareerAgentSideEffectClass.PROVIDER_COMPUTE),
            normalized_params=(("job_id", "job-1"),),
            fact_fingerprint="facts-v5",
        )

    with pytest.raises(CareerAgentExecutionGateError, match="business write"):
        gate.evaluate(
            definition=_definition(side_effect_class=CareerAgentSideEffectClass.BUSINESS_WRITE),
            normalized_params=(("job_id", "job-1"),),
            fact_fingerprint="facts-v5",
        )
