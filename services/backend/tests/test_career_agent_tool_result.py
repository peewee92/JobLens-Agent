import pytest

from app.agent.tool_result import (
    AgentContextRef,
    AgentContextTier,
    AgentToolResult,
    AgentToolResultStatus,
    CareerAgentErrorClass,
    CareerAgentErrorClassifier,
    CareerAgentErrorDisposition,
)


def test_tool_result_keeps_bounded_refs_and_machine_readable_status() -> None:
    result = AgentToolResult(
        status=AgentToolResultStatus.SUCCESS,
        summary="Ranking completed for the governed job scope.",
        data_refs=(AgentContextRef(tier=AgentContextTier.P1, entity_id="ranking-1", version="v3", fingerprint="fp-rank"),),
        grounding_refs=(AgentContextRef(tier=AgentContextTier.P2, entity_id="match-7", version="v5", fingerprint="fp-match"),),
        provider_calls=0,
        retryable=False,
        result_fingerprint="fp-result",
    )

    assert result.status is AgentToolResultStatus.SUCCESS
    assert result.data_refs[0].entity_id == "ranking-1"
    assert result.grounding_refs[0].tier is AgentContextTier.P2


def test_context_refs_require_identity_version_and_fingerprint() -> None:
    with pytest.raises(ValueError, match="identity"):
        AgentContextRef(tier=AgentContextTier.P0, entity_id="", version="v1", fingerprint="fp")


def test_tool_result_rejects_unbounded_summary_and_invalid_provider_count() -> None:
    with pytest.raises(ValueError, match="summary"):
        AgentToolResult(status=AgentToolResultStatus.SUCCESS, summary="x" * 1001, result_fingerprint="fp")
    with pytest.raises(ValueError, match="provider_calls"):
        AgentToolResult(status=AgentToolResultStatus.SUCCESS, summary="ok", provider_calls=-1, result_fingerprint="fp")


def test_permission_stale_and_invariant_errors_fail_closed_without_retry() -> None:
    classifier = CareerAgentErrorClassifier()

    permission = classifier.classify(CareerAgentErrorClass.PERMISSION_OR_RELEASE_GATE)
    stale = classifier.classify(CareerAgentErrorClass.STALE_STATE)
    invariant = classifier.classify(CareerAgentErrorClass.WORKFLOW_INVARIANT)

    assert permission.disposition is CareerAgentErrorDisposition.BLOCK
    assert permission.retryable is False
    assert stale.disposition is CareerAgentErrorDisposition.ABORT_RUN
    assert stale.retryable is False
    assert invariant.disposition is CareerAgentErrorDisposition.FAIL
    assert invariant.retryable is False


def test_transient_provider_and_invalid_params_have_bounded_retry_policy() -> None:
    classifier = CareerAgentErrorClassifier()

    invalid = classifier.classify(CareerAgentErrorClass.INVALID_TOOL_PARAMS)
    transient = classifier.classify(CareerAgentErrorClass.TRANSIENT_NETWORK)
    provider = classifier.classify(CareerAgentErrorClass.PROVIDER_TRANSIENT)

    assert invalid.disposition is CareerAgentErrorDisposition.REPLAN_ONCE
    assert invalid.max_retries == 1
    assert transient.disposition is CareerAgentErrorDisposition.RETRY_BOUNDED
    assert transient.max_retries == 1
    assert provider.disposition is CareerAgentErrorDisposition.RETRY_EXISTING_POLICY
    assert provider.retryable is True


def test_clarification_effect_and_context_budget_route_to_governed_actions() -> None:
    classifier = CareerAgentErrorClassifier()

    clarification = classifier.classify(CareerAgentErrorClass.CLARIFICATION_REQUIRED)
    effect = classifier.classify(CareerAgentErrorClass.EFFECT_APPROVAL_REQUIRED)
    context = classifier.classify(CareerAgentErrorClass.CONTEXT_BUDGET_EXCEEDED)

    assert clarification.disposition is CareerAgentErrorDisposition.ASK_CLARIFICATION
    assert effect.disposition is CareerAgentErrorDisposition.PENDING_ACTION
    assert context.disposition is CareerAgentErrorDisposition.COMPACT_REFS
    assert context.retryable is True
