from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.agent.context import CareerAgentContext, CareerAgentJobContext
from app.agent.intent import CareerIntent, CareerIntentResolutionContext, CareerIntentRouter
from app.agent.tool_registry import CareerAgentToolRegistry
from app.agent.tool_selection import CareerAgentToolSelector

# This regression was written before the runner existed so the missing Tool
# Selection gate was observable first; the runner now satisfies it.
from app.evals.career_tool_selection import (
    ToolSelectionEvalAdapter,
    ToolSelectionEvalCase,
    ToolSelectionEvalCategory,
    ToolSelectionEvalContext,
    ToolSelectionEvalExpected,
    ToolSelectionEvalNoToolReason,
    ToolSelectionEvalOutcome,
    ToolSelectionEvalReplayModel,
    evaluate_career_tool_selections,
    load_career_tool_selection_eval_dataset,
    validate_career_tool_selection_release_dataset,
)


class _CountingRanking:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        include_blocked: bool = False,
        top_n: int | None = None,
    ) -> object:
        self.calls.append(tuple(job_ids))
        return {"jobIds": list(job_ids), "includeBlocked": include_blocked}


class _CountingGaps:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def execute(self, command: object) -> object:
        self.calls.append(command)
        return {"cohortId": getattr(command, "cohort_id", None)}


class _CountingPreparation:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, job_id: str) -> object:
        self.calls.append(job_id)
        return {"jobId": job_id}


class _WorkflowStubs:
    """Record-only workflows prove rejection paths never reach business code."""

    def __init__(self) -> None:
        self.ranking = _CountingRanking()
        self.gaps = _CountingGaps()
        self.preparation = _CountingPreparation()

    @property
    def invocations(self) -> int:
        return len(self.ranking.calls) + len(self.gaps.calls) + len(self.preparation.calls)

    def registry(self) -> CareerAgentToolRegistry:
        return CareerAgentToolRegistry(
            ranking=self.ranking,
            target_cohort_gaps=self.gaps,
            job_preparation=self.preparation,
        )


def _adapter(stubs: _WorkflowStubs, cases: tuple[ToolSelectionEvalCase, ...]) -> ToolSelectionEvalAdapter:
    registry = stubs.registry()
    return ToolSelectionEvalAdapter(
        router=CareerIntentRouter(model=ToolSelectionEvalReplayModel.from_cases(cases)),
        selector=CareerAgentToolSelector(registry=registry),
        registry=registry,
    )


def _case(
    *,
    case_id: str = "case-1",
    category: ToolSelectionEvalCategory = ToolSelectionEvalCategory.CORRECT_TOOL,
    message: str = "Rank this batch.",
    context: ToolSelectionEvalContext | None = None,
    goals: tuple[str, ...] = ("rank_jobs",),
    current_job_required: bool = False,
    needs_clarification: bool = False,
    clarification_question: str | None = None,
    unsupported_request: str | None = None,
    expected: ToolSelectionEvalExpected | None = None,
    argument_probe: dict[str, object] | None = None,
) -> ToolSelectionEvalCase:
    return ToolSelectionEvalCase(
        case_id=case_id,
        category=category,
        message=message,
        context=context or ToolSelectionEvalContext(),
        intent_payload={
            "goals": list(goals),
            "referenced_job_ids": [],
            "current_job_required": current_job_required,
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
            "unsupported_request": unsupported_request,
        },
        expected=expected
        or ToolSelectionEvalExpected(
            outcome=ToolSelectionEvalOutcome.SELECTED,
            tools=("rank_match_reports",),
            reason=None,
        ),
        argument_probe=argument_probe,
    )


def test_release_dataset_meets_prd_152_minimums() -> None:
    cases = load_career_tool_selection_eval_dataset()
    counts: dict[ToolSelectionEvalCategory, int] = {}
    for case in cases:
        counts[case.category] = counts.get(case.category, 0) + 1

    assert len(cases) == 44
    assert counts[ToolSelectionEvalCategory.CORRECT_TOOL] == 10
    assert counts[ToolSelectionEvalCategory.FORBIDDEN_TOOL] == 8
    assert counts[ToolSelectionEvalCategory.UNNECESSARY_TOOL] == 6
    assert counts[ToolSelectionEvalCategory.WRONG_JOB_SCOPE] == 8
    assert counts[ToolSelectionEvalCategory.WRONG_ARGUMENT] == 6
    assert counts[ToolSelectionEvalCategory.NO_TOOL_ANSWER] == 6


def test_release_dataset_validation_rejects_missing_category_minimums() -> None:
    case = _case()

    with pytest.raises(ValueError, match="at least 44"):
        validate_career_tool_selection_release_dataset(cases=(case,))


def test_release_dataset_validation_rejects_duplicate_case_ids() -> None:
    cases = load_career_tool_selection_eval_dataset()
    duplicated = cases + (cases[0],)

    with pytest.raises(ValueError, match="duplicate"):
        validate_career_tool_selection_release_dataset(cases=duplicated)


def test_tool_selection_gate_passes_for_frozen_cohort_against_real_core() -> None:
    cases = load_career_tool_selection_eval_dataset()
    stubs = _WorkflowStubs()

    report = evaluate_career_tool_selections(adapter=_adapter(stubs, cases), cases=cases)

    failures = {
        result.case_id: result.failure_reasons
        for result in report.case_results
        if not result.passed
    }
    assert failures == {}
    assert report.gate_passed is True
    assert report.total_cases == 44
    assert report.provider_attempts == 0
    assert report.provider_completed == 0
    assert report.business_writes == 0
    assert report.workflow_invocations == 0


def test_forbidden_goal_fails_closed_without_selecting_any_tool() -> None:
    cases = load_career_tool_selection_eval_dataset()
    forbidden = tuple(
        case for case in cases if case.category is ToolSelectionEvalCategory.FORBIDDEN_TOOL
    )
    stubs = _WorkflowStubs()

    report = evaluate_career_tool_selections(
        adapter=_adapter(stubs, cases),
        cases=forbidden,
        require_release_dataset=False,
    )

    assert all(result.passed for result in report.case_results)
    assert stubs.invocations == 0


def test_wrong_job_scope_never_widens_governed_scope() -> None:
    cases = load_career_tool_selection_eval_dataset()
    scoped = tuple(
        case for case in cases if case.category is ToolSelectionEvalCategory.WRONG_JOB_SCOPE
    )
    stubs = _WorkflowStubs()

    report = evaluate_career_tool_selections(
        adapter=_adapter(stubs, cases),
        cases=scoped,
        require_release_dataset=False,
    )

    assert all(result.passed for result in report.case_results)
    assert stubs.invocations == 0
    assert stubs.preparation.calls == []


def test_invalid_argument_is_rejected_before_workflow_invocation() -> None:
    cases = load_career_tool_selection_eval_dataset()
    arguments = tuple(
        case for case in cases if case.category is ToolSelectionEvalCategory.WRONG_ARGUMENT
    )
    stubs = _WorkflowStubs()

    report = evaluate_career_tool_selections(
        adapter=_adapter(stubs, cases),
        cases=arguments,
        require_release_dataset=False,
    )

    assert all(result.passed for result in report.case_results)
    assert report.workflow_invocations == 0


def test_no_tool_paths_are_distinguished() -> None:
    cases = load_career_tool_selection_eval_dataset()
    no_tool = tuple(
        case for case in cases if case.category is ToolSelectionEvalCategory.NO_TOOL_ANSWER
    )
    reasons = {case.expected.reason for case in no_tool}

    assert reasons == {
        ToolSelectionEvalNoToolReason.CLARIFICATION,
        ToolSelectionEvalNoToolReason.UNSUPPORTED,
    }

    stubs = _WorkflowStubs()
    report = evaluate_career_tool_selections(
        adapter=_adapter(stubs, cases),
        cases=no_tool,
        require_release_dataset=False,
    )

    assert all(result.passed for result in report.case_results)
    assert stubs.invocations == 0


def test_unnecessary_tool_path_reports_sufficient_facts_without_execution() -> None:
    cases = load_career_tool_selection_eval_dataset()
    unnecessary = tuple(
        case for case in cases if case.category is ToolSelectionEvalCategory.UNNECESSARY_TOOL
    )

    assert all(
        case.expected.outcome is ToolSelectionEvalOutcome.NO_TOOL for case in unnecessary
    )
    assert all(
        case.expected.reason is ToolSelectionEvalNoToolReason.SUFFICIENT_FACTS
        for case in unnecessary
    )

    stubs = _WorkflowStubs()
    report = evaluate_career_tool_selections(
        adapter=_adapter(stubs, cases),
        cases=unnecessary,
        require_release_dataset=False,
    )

    assert all(result.passed for result in report.case_results)
    assert stubs.invocations == 0


def test_gate_reports_contract_violation_for_exactly_one_case() -> None:
    cases = load_career_tool_selection_eval_dataset()
    stubs = _WorkflowStubs()
    adapter = _adapter(stubs, cases)
    tampered = ToolSelectionEvalAdapter(
        router=CareerIntentRouter(
            model=ToolSelectionEvalReplayModel.from_cases(cases).tampered(
                cases[0].message, goals=("review_application",)
            )
        ),
        selector=adapter.selector,
        registry=adapter.registry,
    )

    report = evaluate_career_tool_selections(adapter=tampered, cases=cases)

    failed = [result for result in report.case_results if not result.passed]
    assert report.gate_passed is False
    assert len(failed) == 1
    assert failed[0].case_id == cases[0].case_id
    assert any("forbidden" in reason for reason in failed[0].failure_reasons)


def test_selected_tools_must_satisfy_read_only_governance_invariants() -> None:
    cases = load_career_tool_selection_eval_dataset()
    stubs = _WorkflowStubs()

    report = evaluate_career_tool_selections(adapter=_adapter(stubs, cases), cases=cases)

    selected = [
        governance
        for result in report.case_results
        for governance in result.governance
    ]
    assert selected
    for governance in selected:
        assert governance.access == "read_only"
        assert governance.side_effect_class == "read_only"
        assert governance.provider_cost_class == "none"
        assert governance.human_gate_requirement == "none"
        assert governance.idempotency_class == "read_only"


def test_provider_and_business_write_budgets_are_enforced() -> None:
    case = _case(goals=("rank_jobs",))

    class _LeakyAdapter(ToolSelectionEvalAdapter):
        def run(self, *, case: ToolSelectionEvalCase):  # type: ignore[override]
            execution = super().run(case=case)
            return replace(execution, provider_attempts=1, business_writes=1)

    stubs = _WorkflowStubs()
    adapter = _adapter(stubs, (case,))

    report = evaluate_career_tool_selections(
        adapter=_LeakyAdapter(
            router=adapter.router,
            selector=adapter.selector,
            registry=adapter.registry,
        ),
        cases=(case,),
        require_release_dataset=False,
    )

    assert report.gate_passed is False
    reasons = report.case_results[0].failure_reasons
    assert any("provider attempts" in reason for reason in reasons)
    assert any("business writes" in reason for reason in reasons)


def test_tool_selection_eval_requires_at_least_one_case() -> None:
    stubs = _WorkflowStubs()

    with pytest.raises(ValueError, match="at least one case"):
        evaluate_career_tool_selections(
            adapter=_adapter(stubs, ()),
            cases=(),
            require_release_dataset=False,
        )


def _write_dataset(tmp_path, rows: list[dict[str, object]]) -> str:
    path = tmp_path / "cohort.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return str(path)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "row-1",
        "category": "correct_tool",
        "message": "Rank these.",
        "context": {"runJobIds": ["job-1"]},
        "intent": {
            "goals": ["rank_jobs"],
            "referenced_job_ids": [],
            "current_job_required": False,
            "needs_clarification": False,
            "clarification_question": None,
            "unsupported_request": None,
        },
        "expected": {
            "outcome": "selected",
            "tools": ["rank_match_reports"],
            "reason": None,
        },
    }
    row.update(overrides)
    return row


def test_loader_rejects_duplicate_messages_because_oracle_is_keyed_by_message(tmp_path) -> None:
    rows = [_row(id="row-1"), _row(id="row-2")]

    with pytest.raises(ValueError, match="unique"):
        load_career_tool_selection_eval_dataset(_write_dataset(tmp_path, rows))


def test_loader_rejects_category_outcome_mismatch(tmp_path) -> None:
    rows = [
        _row(
            expected={"outcome": "no_tool", "tools": [], "reason": "clarification"},
        )
    ]

    with pytest.raises(ValueError, match="correct_tool case must expect a selection"):
        load_career_tool_selection_eval_dataset(_write_dataset(tmp_path, rows))


def test_loader_rejects_unknown_tool_names(tmp_path) -> None:
    rows = [_row(expected={"outcome": "selected", "tools": ["send_email"], "reason": None})]

    with pytest.raises(ValueError, match="unknown tool"):
        load_career_tool_selection_eval_dataset(_write_dataset(tmp_path, rows))


def test_direct_selector_must_not_select_preparation_without_governed_current_job() -> None:
    from app.agent.tool_selection import CareerAgentToolSelectionError
    from app.agent.intent import CareerIntentGoal

    stubs = _WorkflowStubs()
    selector = CareerAgentToolSelector(registry=stubs.registry())

    with pytest.raises(CareerAgentToolSelectionError):
        selector.select(CareerIntent(goals=(CareerIntentGoal.REVIEW_APPLICATION,)))


def test_eval_context_grounds_current_job_for_preparation_selection() -> None:
    cases = load_career_tool_selection_eval_dataset()
    prepared = tuple(
        case
        for case in cases
        if case.category is ToolSelectionEvalCategory.CORRECT_TOOL
        and case.expected.tools == ("job_preparation",)
    )
    assert prepared
    assert all(case.context.current_job_id for case in prepared)

    adapter = _adapter(_WorkflowStubs(), cases)
    for case in prepared:
        execution = adapter.run(case=case)
        assert execution.outcome is ToolSelectionEvalOutcome.SELECTED
        assert execution.tools == ("job_preparation",)


def test_governed_context_builder_contract_is_reusable_by_eval_fixtures() -> None:
    context = CareerAgentContext(
        usable=True,
        confirmation_boundary="confirmed_profile_v1",
        profile=None,
        search_intent=None,
        current_job=CareerAgentJobContext(
            id="job-101", title="AI Product Engineer", company="Acme", area=None
        ),
        relevant_evidence=(),
        blockers=(),
        blocker_messages=(),
    )

    assert context.usable is True
    assert context.current_job is not None
    assert context.current_job.id == "job-101"
    assert CareerIntentResolutionContext(run_job_ids=("job-101",)).run_job_ids == ("job-101",)
