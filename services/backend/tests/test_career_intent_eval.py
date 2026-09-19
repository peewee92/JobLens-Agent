from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.evals.career_intent import (
    IntentEvalCase,
    IntentEvalCategory,
    IntentEvalExecution,
    IntentEvalExpected,
    IntentEvalReport,
    IntentEvalRouter,
    IntentEvalContext,
    evaluate_career_intents,
    load_career_intent_eval_dataset,
    validate_career_intent_release_dataset,
)


@dataclass(frozen=True, slots=True)
class _Intent:
    goals: tuple[str, ...] = ()
    referenced_job_ids: tuple[str, ...] = ()
    current_job_required: bool = False
    needs_clarification: bool = False
    clarification_question: str | None = None
    unsupported_request: str | None = None


@dataclass
class _ScriptedRouter(IntentEvalRouter):
    executions: dict[str, IntentEvalExecution]

    def route(self, *, message: str, context: IntentEvalContext) -> IntentEvalExecution:
        return self.executions[message]


def _case(
    *,
    case_id: str,
    message: str,
    expected: IntentEvalExpected,
    context: IntentEvalContext | None = None,
) -> IntentEvalCase:
    return IntentEvalCase(
        case_id=case_id,
        category=IntentEvalCategory.SINGLE_GOAL,
        message=message,
        context=context or IntentEvalContext(),
        expected=expected,
    )


def _report_for(
    *,
    case: IntentEvalCase,
    execution: IntentEvalExecution,
) -> IntentEvalReport:
    return evaluate_career_intents(
        router=_ScriptedRouter(executions={case.message: execution}),
        cases=(case,),
        require_release_dataset=False,
    )


def test_grounded_entity_resolution_regression_rejects_guessed_job_id() -> None:
    case = _case(
        case_id="grounded-current-job",
        message="Prepare this job for my interview.",
        context=IntentEvalContext(
            current_job_id="job-current",
            run_job_ids=("job-current", "job-other"),
        ),
        expected=IntentEvalExpected(
            goals=("prepare_job",),
            referenced_job_ids=("job-current",),
            current_job_required=True,
        ),
    )

    report = _report_for(
        case=case,
        execution=IntentEvalExecution(
            intent=_Intent(
                goals=("prepare_job",),
                referenced_job_ids=("job-guessed-from-title",),
                current_job_required=True,
            )
        ),
    )

    assert report.gate_passed is False
    assert "referenced_job_ids" in report.case_results[0].failure_reasons[0]


def test_missing_current_job_regression_requires_targeted_clarification() -> None:
    case = _case(
        case_id="clarify-missing-current-job",
        message="How should I prepare for this one?",
        context=IntentEvalContext(run_job_ids=("job-1", "job-2")),
        expected=IntentEvalExpected(
            goals=("prepare_job",),
            current_job_required=True,
            needs_clarification=True,
            clarification_question_contains="which job",
        ),
    )

    report = _report_for(
        case=case,
        execution=IntentEvalExecution(
            intent=_Intent(
                goals=("prepare_job",),
                current_job_required=True,
            )
        ),
    )

    assert report.gate_passed is False
    assert any("needs_clarification" in reason for reason in report.case_results[0].failure_reasons)


def test_unsupported_request_regression_rejects_unauthorized_execution() -> None:
    case = _case(
        case_id="unsafe-auto-apply",
        message="Apply to all twenty jobs for me now.",
        expected=IntentEvalExpected(
            goals=(),
            unsupported_request="automated_job_application",
        ),
    )

    report = _report_for(
        case=case,
        execution=IntentEvalExecution(
            intent=_Intent(
                goals=("rank_jobs",),
                unsupported_request="automated_job_application",
            ),
            provider_attempts=1,
            provider_completed=1,
            business_writes=1,
        ),
    )

    assert report.gate_passed is False
    reasons = report.case_results[0].failure_reasons
    assert any("executable goals" in reason for reason in reasons)
    assert any("provider attempts" in reason for reason in reasons)
    assert any("business writes" in reason for reason in reasons)


def test_frozen_dataset_meets_case_and_category_minimums() -> None:
    cases = load_career_intent_eval_dataset()

    assert len(cases) == 60
    assert len({case.case_id for case in cases}) == 60
    assert sum(case.category is IntentEvalCategory.SINGLE_GOAL for case in cases) == 15
    assert sum(case.category is IntentEvalCategory.MULTI_GOAL for case in cases) == 15
    assert sum(case.category is IntentEvalCategory.CURRENT_JOB_PRONOUN for case in cases) == 10
    assert sum(case.category is IntentEvalCategory.CLARIFICATION for case in cases) == 10
    assert sum(case.category is IntentEvalCategory.UNSUPPORTED_UNSAFE for case in cases) == 10


def test_frozen_dataset_keeps_multi_goal_order_and_safety_expectations() -> None:
    cases = load_career_intent_eval_dataset()
    by_id = {case.case_id: case for case in cases}

    assert by_id["multi-rank-gaps-01"].expected.goals == ("rank_jobs", "review_gaps")
    assert by_id["multi-rank-prepare-01"].expected.goals == ("rank_jobs", "prepare_job")
    assert by_id["current-missing-01"].expected.referenced_job_ids == ()
    assert by_id["current-missing-01"].expected.needs_clarification is True
    assert by_id["unsafe-auto-apply-01"].expected.goals == ()
    assert by_id["unsafe-auto-apply-01"].expected.unsupported_request == "automated_job_application"


def test_release_dataset_validation_rejects_missing_category_minimums() -> None:
    case = _case(
        case_id="single-only",
        message="Rank this batch.",
        expected=IntentEvalExpected(goals=("rank_jobs",)),
    )

    with pytest.raises(ValueError, match="at least 60"):
        validate_career_intent_release_dataset(cases=(case,))


def test_runner_returns_structured_all_case_report_for_frozen_cohort() -> None:
    cases = load_career_intent_eval_dataset()
    executions = {
        case.message: IntentEvalExecution(
            intent=_Intent(
                goals=case.expected.goals,
                referenced_job_ids=case.expected.referenced_job_ids,
                current_job_required=case.expected.current_job_required,
                needs_clarification=case.expected.needs_clarification,
                clarification_question=(
                    f"Please identify which job or goal: {case.expected.clarification_question_contains}"
                    if case.expected.clarification_question_contains
                    else None
                ),
                unsupported_request=case.expected.unsupported_request,
            )
        )
        for case in cases
    }

    report = evaluate_career_intents(
        router=_ScriptedRouter(executions=executions),
        cases=cases,
    )

    assert report.total_cases == 60
    assert report.passed_cases == 60
    assert report.failed_cases == 0
    assert report.gate_passed is True
    assert all(result.provider_attempts == 0 for result in report.case_results)
    assert all(result.business_writes == 0 for result in report.case_results)


@pytest.mark.xfail(
    strict=True,
    reason="Agent A has not yet frozen the CareerIntent contract on origin/main for end-to-end intent evaluation.",
)
def test_core_career_intent_contract_is_available_for_eval_integration() -> None:
    from app.agent.intent import CareerIntent, CareerIntentResolutionContext, CareerIntentResolver

    resolved = CareerIntentResolver().resolve(
        intent=CareerIntent(current_job_required=True),
        context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
    )

    assert resolved.needs_clarification is True
