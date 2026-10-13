from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agent.context import (
    CareerAgentContext,
    CareerAgentContextBlocker,
    CareerAgentJobContext,
)
from app.agent.tool_registry import (
    CareerAgentToolName,
    CareerAgentToolRegistry,
    JobPreparationRequest,
)
from app.mcp.adapter import JobLensMcpAdapter
from app.mcp.schemas import (
    JobPreparationInput,
    RankMatchReportsInput,
    TargetCohortGapsInput,
)


def _context(*, current_job: str | None = None, usable: bool = True) -> CareerAgentContext:
    return CareerAgentContext(
        usable=usable,
        confirmation_boundary="released" if usable else "blocked",
        profile=object() if usable else None,  # type: ignore[arg-type]
        search_intent=object() if usable else None,  # type: ignore[arg-type]
        current_job=(
            CareerAgentJobContext(current_job, "Role", "Company", None)
            if current_job is not None and usable
            else None
        ),
        relevant_evidence=(),
        blockers=() if usable else (CareerAgentContextBlocker.CAREER_CONTEXT_NOT_RELEASED,),
        blocker_messages=() if usable else ("Career context needs a human release.",),
    )


class ContextBuilder:
    def __init__(self, context: CareerAgentContext):
        self.context = context
        self.calls: list[dict] = []

    def build(self, **kwargs):
        self.calls.append(kwargs)
        return self.context


class Registry:
    def __init__(self, output=object()):
        self.output = output
        self.calls: list[dict] = []

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return self.output


class Projection:
    @classmethod
    def from_details(cls, _output):
        return SimpleNamespace(model_dump=lambda **_kwargs: {"kind": "ranking"})

    @classmethod
    def from_result(cls, _output):
        return SimpleNamespace(model_dump=lambda **_kwargs: {"kind": "facts"})


def _adapter(builder, registry) -> JobLensMcpAdapter:
    return JobLensMcpAdapter(
        context_builder=builder,
        tool_registry=registry,
        trace_id_factory=lambda: "mcp_test_trace",
    )


def test_rank_request_reaches_registry_with_explicit_ids_and_public_projection(monkeypatch) -> None:
    import app.mcp.adapter as module

    monkeypatch.setattr(module, "BatchMatchRankingResponse", Projection)
    builder = ContextBuilder(_context())
    registry = Registry()

    result = _adapter(builder, registry).rank_match_reports(
        RankMatchReportsInput(job_ids=["job_1", "job_1", "job_2"], top_n=2)
    )

    assert result.ok is True
    assert result.data == {"kind": "ranking"}
    assert result.meta.provider_calls == result.meta.business_writes == 0
    assert builder.calls == [{}]
    request = registry.calls[0]["request"]
    assert request.job_ids == ("job_1", "job_1", "job_2")
    assert request.top_n == 2


def test_gap_request_hides_internal_cohort_identity_and_uses_explicit_selection(monkeypatch) -> None:
    import app.mcp.adapter as module

    monkeypatch.setattr(module, "TargetCohortGapResponse", Projection)
    builder = ContextBuilder(_context())
    registry = Registry()

    result = _adapter(builder, registry).target_cohort_gaps(
        TargetCohortGapsInput(selected_job_ids=["job_1", "job_2"])
    )

    assert result.ok is True
    request = registry.calls[0]["request"]
    assert request.selected_job_ids == ("job_1", "job_2")
    assert request.cohort_id.startswith("mcp_cohort_")
    assert "cohort" not in result.data


def test_preparation_builds_context_for_the_same_explicit_job(monkeypatch) -> None:
    import app.mcp.adapter as module

    monkeypatch.setattr(module, "JobPreparationResponse", Projection)
    builder = ContextBuilder(_context(current_job="job_1"))
    registry = Registry()

    result = _adapter(builder, registry).job_preparation(JobPreparationInput(job_id="job_1"))

    assert result.ok is True
    assert builder.calls == [{"current_job_id": "job_1"}]
    assert registry.calls[0]["tool"] is CareerAgentToolName.JOB_PREPARATION


def test_unreleased_context_fails_before_registry_invocation() -> None:
    builder = ContextBuilder(_context(usable=False))
    registry = Registry()

    result = _adapter(builder, registry).rank_match_reports(RankMatchReportsInput(job_ids=["job_1"]))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "context_not_released"
    assert registry.calls == []


def test_empty_explicit_job_selection_is_rejected_by_external_schema() -> None:
    with pytest.raises(ValidationError):
        TargetCohortGapsInput(selected_job_ids=[])


def test_preparation_context_mismatch_is_rejected_before_underlying_workflow() -> None:
    class Workflows:
        def __init__(self):
            self.preparation_calls = 0

        def ranking(self, *_args, **_kwargs):
            raise AssertionError("not used")

        def gaps(self, *_args, **_kwargs):
            raise AssertionError("not used")

        def preparation(self, *_args, **_kwargs):
            self.preparation_calls += 1

    workflows = Workflows()
    registry = CareerAgentToolRegistry(
        ranking=SimpleNamespace(execute=workflows.ranking),
        target_cohort_gaps=SimpleNamespace(execute=workflows.gaps),
        job_preparation=SimpleNamespace(execute=workflows.preparation),
    )
    # Simulates a stale/malicious context source: the adapter passes job_1 but
    # the governed context carries job_2. Registry must stop it before execute.
    builder = ContextBuilder(_context(current_job="job_2"))

    result = _adapter(builder, registry).job_preparation(JobPreparationInput(job_id="job_1"))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "invalid_argument"
    assert workflows.preparation_calls == 0
