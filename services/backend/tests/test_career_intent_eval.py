from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.agent.intent import CareerIntentModel, CareerIntentRouter
from app.evals.career_intent import (
    CareerIntentCoreEvalAdapter,
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


def _clarification_question(case: IntentEvalCase) -> str:
    """Model-owned clarification wording, or the Core resolver's wording."""

    substring = case.expected.clarification_question_contains
    if substring:
        return f"Clarification required: please specify the {substring}."
    return "请先明确你指的是哪个岗位。"


def _replay_payload(case: IntentEvalCase) -> dict[str, object]:
    """Deterministic stand-in model output for one frozen Eval case.

    This is a frozen oracle, not a router: it only decodes the case's expectation
    into the shape the Core model seam must return, so the real
    ``CareerIntentRouter`` parse/validate/ground path can be exercised without a
    Provider call. It must never be treated as evidence of model accuracy.
    """

    from_current_job = case.context.current_job_id is not None
    return {
        "goals": list(case.expected.goals),
        "referenced_job_ids": (
            [] if from_current_job else list(case.expected.referenced_job_ids)
        ),
        "current_job_required": case.expected.current_job_required,
        "needs_clarification": case.expected.needs_clarification,
        "clarification_question": (
            _clarification_question(case) if case.expected.needs_clarification else None
        ),
        "unsupported_request": case.expected.unsupported_request,
        "confidence": 0.9,
        "reasoning_summary": "frozen intent eval replay.",
    }


class _ReplayIntentModel(CareerIntentModel):
    """Deterministic frozen-oracle model standing in for the provider seam."""

    def __init__(
        self,
        cases: tuple[IntentEvalCase, ...],
        payloads: tuple[dict[str, object], ...],
        *,
        tamper=None,
    ) -> None:
        self._cases = dict(zip((case.message for case in cases), cases))
        self._payloads = dict(zip((case.message for case in cases), payloads))
        self._tamper = tamper
        self.routed_messages: list[str] = []

    @classmethod
    def replaying(
        cls,
        cases: tuple[IntentEvalCase, ...],
        *,
        tamper=None,
    ) -> "_ReplayIntentModel":
        return cls(
            cases,
            tuple(_replay_payload(case) for case in cases),
            tamper=tamper,
        )

    def route(self, user_message: str) -> dict[str, object]:
        self.routed_messages.append(user_message)
        payload = self._payloads[user_message]
        if self._tamper is None:
            return payload
        return self._tamper(self._cases[user_message], payload)


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
                    _clarification_question(case)
                    if case.expected.needs_clarification
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


def test_core_adapter_grounds_current_job_from_eval_context() -> None:
    case = _case(
        case_id="adapter-current-job",
        message="Prepare this job for my interview.",
        context=IntentEvalContext(run_job_ids=("job-current", "job-other")),
        expected=IntentEvalExpected(
            goals=("prepare_job",),
            current_job_required=True,
        ),
    )
    model = _ReplayIntentModel.replaying((case,))
    adapter = CareerIntentCoreEvalAdapter(router=CareerIntentRouter(model=model))

    grounded = adapter.route(
        message=case.message,
        context=IntentEvalContext(
            current_job_id="job-current",
            run_job_ids=("job-current", "job-other"),
        ),
    )
    missing = adapter.route(
        message=case.message,
        context=IntentEvalContext(run_job_ids=("job-other",)),
    )

    assert grounded.intent.referenced_job_ids == ("job-current",)
    assert grounded.intent.needs_clarification is False
    assert missing.intent.referenced_job_ids == ()
    assert missing.intent.goals == ()
    assert missing.intent.needs_clarification is True
    assert missing.intent.clarification_question


def test_core_router_passes_frozen_intent_release_gate_end_to_end() -> None:
    cases = load_career_intent_eval_dataset()
    model = _ReplayIntentModel.replaying(cases)
    adapter = CareerIntentCoreEvalAdapter(
        router=CareerIntentRouter(model=model)
    )

    report = evaluate_career_intents(router=adapter, cases=cases)

    assert model.routed_messages == [case.message for case in cases]
    assert report.total_cases == 60
    assert report.failed_cases == 0, [
        (result.case_id, result.failure_reasons)
        for result in report.case_results
        if not result.passed
    ]
    assert report.gate_passed is True
    assert all(result.provider_attempts == 0 for result in report.case_results)
    assert all(result.provider_completed == 0 for result in report.case_results)
    assert all(result.business_writes == 0 for result in report.case_results)


def test_core_router_gate_reports_contract_regressions_per_case() -> None:
    cases = load_career_intent_eval_dataset()
    model = _ReplayIntentModel.replaying(
        cases,
        tamper=lambda case, payload: (
            {**payload, "referenced_job_ids": ["job-not-in-scope"]}
            if case.case_id == "single-prepare-01"
            else payload
        ),
    )
    adapter = CareerIntentCoreEvalAdapter(
        router=CareerIntentRouter(model=model)
    )

    report = evaluate_career_intents(router=adapter, cases=cases)

    assert report.gate_passed is False
    assert report.failed_cases == 1
    failed = {result.case_id: result for result in report.case_results}
    assert failed["single-prepare-01"].passed is False
