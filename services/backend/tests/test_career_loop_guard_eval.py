from __future__ import annotations

from dataclasses import replace

import pytest

# This regression was written before the runner existed so the missing Loop Guard
# gate was observable first; the runner now satisfies it.
from app.evals.career_loop_guard import (
    LoopGuardEvalCase,
    LoopGuardEvalCategory,
    LoopGuardEvalDriver,
    LoopGuardEvalExpected,
    LoopGuardEvalStep,
    LoopGuardEvalStepType,
    evaluate_career_loop_guard,
    load_career_loop_guard_eval_dataset,
    validate_career_loop_guard_release_dataset,
)


def _turn() -> LoopGuardEvalStep:
    return LoopGuardEvalStep(type=LoopGuardEvalStepType.TURN)


def _provider() -> LoopGuardEvalStep:
    return LoopGuardEvalStep(type=LoopGuardEvalStepType.PROVIDER_CALL)


def _tool(
    *,
    tool: str = "rank_match_reports",
    arguments: str = "args-1",
    inputs: str = "input-1",
    transient_retry: bool = False,
) -> LoopGuardEvalStep:
    return LoopGuardEvalStep(
        type=LoopGuardEvalStepType.TOOL_CALL,
        tool=tool,
        arguments_fingerprint=arguments,
        input_fingerprint=inputs,
        transient_retry=transient_retry,
    )


def _obs(*, state: str = "s1", blocker: str = "b1", fact: str = "f1") -> LoopGuardEvalStep:
    return LoopGuardEvalStep(
        type=LoopGuardEvalStepType.OBSERVATION,
        state_fingerprint=state,
        blocker_fingerprint=blocker,
        fact_fingerprint=fact,
    )


def _error(*, code: str = "unknown_tool", retryable: bool = True) -> LoopGuardEvalStep:
    return LoopGuardEvalStep(
        type=LoopGuardEvalStepType.ERROR,
        error_code=code,
        error_retryable=retryable,
    )


def _case(
    *,
    case_id: str = "case-1",
    category: LoopGuardEvalCategory = LoopGuardEvalCategory.MAX_TURNS,
    budget: dict[str, int] | None = None,
    steps: tuple[LoopGuardEvalStep, ...] = (),
    expected: LoopGuardEvalExpected | None = None,
) -> LoopGuardEvalCase:
    return LoopGuardEvalCase(
        case_id=case_id,
        category=category,
        budget_overrides=budget or {},
        steps=steps,
        expected=expected
        or LoopGuardEvalExpected(stopped=False, steps_applied=len(steps)),
    )


def test_release_dataset_meets_loop_guard_minimums() -> None:
    cases = load_career_loop_guard_eval_dataset()
    counts: dict[LoopGuardEvalCategory, int] = {}
    for case in cases:
        counts[case.category] = counts.get(case.category, 0) + 1

    assert len(cases) == 26
    assert counts[LoopGuardEvalCategory.MAX_TURNS] == 3
    assert counts[LoopGuardEvalCategory.MAX_TOOL_CALLS] == 3
    assert counts[LoopGuardEvalCategory.PROVIDER_BUDGET] == 2
    assert counts[LoopGuardEvalCategory.RETRY_BOUND] == 3
    assert counts[LoopGuardEvalCategory.SAME_TOOL] == 3
    assert counts[LoopGuardEvalCategory.NO_PROGRESS] == 3
    assert counts[LoopGuardEvalCategory.UNKNOWN_TOOL] == 3
    assert counts[LoopGuardEvalCategory.INVALID_TOOL_PARAMS] == 3
    assert counts[LoopGuardEvalCategory.HEALTHY_PROGRESS] == 3


def test_release_dataset_validation_rejects_missing_category_minimums() -> None:
    with pytest.raises(ValueError, match="at least 26"):
        validate_career_loop_guard_release_dataset(cases=(_case(),))


def test_loop_guard_gate_passes_for_frozen_cohort_against_real_core() -> None:
    cases = load_career_loop_guard_eval_dataset()

    report = evaluate_career_loop_guard(driver=LoopGuardEvalDriver(), cases=cases)

    failures = {
        result.case_id: result.failure_reasons
        for result in report.case_results
        if not result.passed
    }
    assert failures == {}
    assert report.gate_passed is True
    assert report.total_cases == 26
    assert report.unclassified_errors == 0
    assert report.retryable_stops == 0
    assert report.healthy_cases_stopped == 0
    assert report.provider_attempts == 0
    assert report.provider_completed == 0
    assert report.business_writes == 0


def test_healthy_progress_cases_never_stop() -> None:
    cases = load_career_loop_guard_eval_dataset()
    healthy = tuple(
        case for case in cases if case.category is LoopGuardEvalCategory.HEALTHY_PROGRESS
    )
    assert len(healthy) == 3

    report = evaluate_career_loop_guard(
        driver=LoopGuardEvalDriver(),
        cases=healthy,
        require_release_dataset=False,
    )

    assert all(result.passed for result in report.case_results)
    assert all(not result.execution.stopped for result in report.case_results)
    assert all(not result.execution.unclassified_error for result in report.case_results)
    assert report.healthy_cases_stopped == 0


def test_same_tool_with_different_arguments_is_not_a_loop() -> None:
    case = _case(
        category=LoopGuardEvalCategory.HEALTHY_PROGRESS,
        budget={"max_same_tool_consecutive": 2},
        steps=(
            _tool(arguments="args-1"),
            _tool(arguments="args-2"),
            _tool(arguments="args-3"),
        ),
        expected=LoopGuardEvalExpected(stopped=False, tool_calls_used=3, steps_applied=3),
    )

    report = evaluate_career_loop_guard(
        driver=LoopGuardEvalDriver(),
        cases=(case,),
        require_release_dataset=False,
    )

    assert report.passed_cases == 1
    assert report.case_results[0].execution.stopped is False


def test_exactly_at_budget_is_allowed_and_exceeding_it_stops() -> None:
    within = _case(
        case_id="within",
        budget={"max_turns": 2},
        steps=(_turn(), _turn()),
        expected=LoopGuardEvalExpected(stopped=False, turns_used=2, steps_applied=2),
    )
    beyond = _case(
        case_id="beyond",
        budget={"max_turns": 2},
        steps=(_turn(), _turn(), _turn()),
        expected=LoopGuardEvalExpected(
            stopped=True,
            stop_code="budget_exhausted",
            stop_retryable=False,
            turns_used=2,
            steps_applied=2,
        ),
    )

    report = evaluate_career_loop_guard(
        driver=LoopGuardEvalDriver(),
        cases=(within, beyond),
        require_release_dataset=False,
    )

    assert report.passed_cases == 2


def test_retry_budget_is_tracked_per_error_code() -> None:
    case = _case(
        category=LoopGuardEvalCategory.RETRY_BOUND,
        budget={"max_retries": 1},
        steps=(
            _error(code="unknown_tool"),
            _error(code="invalid_tool_params"),
            _error(code="unknown_tool"),
        ),
        expected=LoopGuardEvalExpected(
            stopped=False,
            retry_outcomes=(
                ("unknown_tool", True),
                ("invalid_tool_params", True),
                ("unknown_tool", False),
            ),
            steps_applied=3,
        ),
    )

    report = evaluate_career_loop_guard(
        driver=LoopGuardEvalDriver(),
        cases=(case,),
        require_release_dataset=False,
    )

    assert report.passed_cases == 1
    assert report.case_results[0].execution.retry_outcomes == (
        ("unknown_tool", True),
        ("invalid_tool_params", True),
        ("unknown_tool", False),
    )


def test_non_retryable_error_bypasses_retry_budget() -> None:
    case = _case(
        category=LoopGuardEvalCategory.INVALID_TOOL_PARAMS,
        budget={"max_retries": 5},
        steps=(_error(code="loop_detected", retryable=False),),
        expected=LoopGuardEvalExpected(
            stopped=False,
            retry_outcomes=(("loop_detected", False),),
            steps_applied=1,
        ),
    )

    report = evaluate_career_loop_guard(
        driver=LoopGuardEvalDriver(),
        cases=(case,),
        require_release_dataset=False,
    )

    assert report.passed_cases == 1


def test_every_stop_is_structured_and_terminal() -> None:
    cases = load_career_loop_guard_eval_dataset()
    stopping = tuple(case for case in cases if case.expected.stopped)
    assert stopping

    report = evaluate_career_loop_guard(
        driver=LoopGuardEvalDriver(),
        cases=stopping,
        require_release_dataset=False,
    )

    assert report.passed_cases == len(stopping)
    for result in report.case_results:
        execution = result.execution
        assert execution.stopped is True
        assert execution.unclassified_error is None
        assert execution.stop_code is not None
        assert execution.stop_retryable is False
    assert report.unclassified_errors == 0
    assert report.retryable_stops == 0


def test_gate_reports_mislabelled_case_for_exactly_one_case() -> None:
    cases = load_career_loop_guard_eval_dataset()
    first = cases[0]
    mislabelled = replace(
        first,
        expected=replace(first.expected, stopped=not first.expected.stopped),
    )
    tampered = (mislabelled,) + cases[1:]

    report = evaluate_career_loop_guard(driver=LoopGuardEvalDriver(), cases=tampered)

    failed = [result for result in report.case_results if not result.passed]
    assert report.gate_passed is False
    assert len(failed) == 1
    assert failed[0].case_id == first.case_id
    assert any("stopped" in reason for reason in failed[0].failure_reasons)


def test_unclassified_stop_is_reported_as_a_violation() -> None:
    case = _case(
        budget={"max_turns": 1},
        steps=(_turn(), _turn()),
        expected=LoopGuardEvalExpected(
            stopped=True,
            stop_code="budget_exhausted",
            stop_retryable=False,
            turns_used=1,
            steps_applied=1,
        ),
    )

    class _LeakyDriver(LoopGuardEvalDriver):
        def run(self, *, case: LoopGuardEvalCase):  # type: ignore[override]
            return replace(
                super().run(case=case),
                unclassified_error="RuntimeError: leaked raw failure",
            )

    report = evaluate_career_loop_guard(
        driver=_LeakyDriver(),
        cases=(case,),
        require_release_dataset=False,
    )

    assert report.gate_passed is False
    assert report.unclassified_errors == 1
    assert any(
        "unclassified" in reason for reason in report.case_results[0].failure_reasons
    )


def test_provider_and_business_write_budgets_are_enforced() -> None:
    case = _case(steps=(_turn(),), expected=LoopGuardEvalExpected(stopped=False, turns_used=1, steps_applied=1))

    class _LeakyDriver(LoopGuardEvalDriver):
        def run(self, *, case: LoopGuardEvalCase):  # type: ignore[override]
            return replace(
                super().run(case=case),
                provider_attempts=1,
                business_writes=1,
            )

    report = evaluate_career_loop_guard(
        driver=_LeakyDriver(),
        cases=(case,),
        require_release_dataset=False,
    )

    assert report.gate_passed is False
    reasons = report.case_results[0].failure_reasons
    assert any("provider attempts" in reason for reason in reasons)
    assert any("business writes" in reason for reason in reasons)


def test_loop_guard_eval_requires_at_least_one_case() -> None:
    with pytest.raises(ValueError, match="at least one case"):
        evaluate_career_loop_guard(
            driver=LoopGuardEvalDriver(),
            cases=(),
            require_release_dataset=False,
        )


def test_loader_rejects_unknown_step_type(tmp_path) -> None:
    path = tmp_path / "cohort.jsonl"
    path.write_text(
        '{"id": "bad-1", "category": "max_turns", "steps": [{"type": "teleport"}],'
        ' "expected": {"stopped": false, "stepsApplied": 1}}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid step type"):
        load_career_loop_guard_eval_dataset(str(path))


def test_loader_rejects_category_expectation_mismatch(tmp_path) -> None:
    path = tmp_path / "cohort.jsonl"
    path.write_text(
        '{"id": "bad-2", "category": "healthy_progress",'
        ' "steps": [{"type": "turn"}, {"type": "turn"}],'
        ' "budget": {"max_turns": 1},'
        ' "expected": {"stopped": true, "stopCode": "budget_exhausted",'
        ' "stopRetryable": false, "turnsUsed": 1, "toolCallsUsed": 0,'
        ' "providerBudgetUsed": 0, "retryOutcomes": [], "stepsApplied": 1}}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="healthy_progress case must not expect a stop"):
        load_career_loop_guard_eval_dataset(str(path))


def test_loader_rejects_retry_outcomes_count_mismatch(tmp_path) -> None:
    path = tmp_path / "cohort.jsonl"
    path.write_text(
        '{"id": "bad-3", "category": "unknown_tool",'
        ' "steps": [{"type": "error", "errorCode": "unknown_tool", "errorRetryable": true}],'
        ' "budget": {"max_retries": 1},'
        ' "expected": {"stopped": false, "stopCode": null, "stopRetryable": null,'
        ' "turnsUsed": 0, "toolCallsUsed": 0, "providerBudgetUsed": 0,'
        ' "retryOutcomes": [], "stepsApplied": 1}}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="one outcome per error step"):
        load_career_loop_guard_eval_dataset(str(path))


def test_loader_rejects_unknown_error_code(tmp_path) -> None:
    path = tmp_path / "cohort.jsonl"
    path.write_text(
        '{"id": "bad-4", "category": "unknown_tool",'
        ' "steps": [{"type": "error", "errorCode": "cosmic_ray", "errorRetryable": true}],'
        ' "expected": {"stopped": false, "stopCode": null, "stopRetryable": null,'
        ' "turnsUsed": 0, "toolCallsUsed": 0, "providerBudgetUsed": 0,'
        ' "retryOutcomes": [["cosmic_ray", true]], "stepsApplied": 1}}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown error code"):
        load_career_loop_guard_eval_dataset(str(path))


def test_dataset_budget_overrides_stay_within_hard_limits() -> None:
    cases = load_career_loop_guard_eval_dataset()
    for case in cases:
        if "max_turns" in case.budget_overrides:
            assert case.budget_overrides["max_turns"] <= 10
