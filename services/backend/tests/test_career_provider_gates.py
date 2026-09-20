"""Tests for the provider-authorized model-quality gates.

These tests never contact a Provider.  They prove that the gate plumbing measures
what it claims to measure, that every safety counter is wired to a real signal,
and — most importantly — that a disabled Provider can never be reported as a pass.
"""
from __future__ import annotations

import pytest

from app.core.config import Settings
from app.evals.career_intent import IntentEvalCase, load_career_intent_eval_dataset
from app.evals.career_provider_gates import (
    GATE_MINIMUM_ACCURACY,
    ProviderGateStatus,
    measure_career_intent_provider_quality,
    measure_career_tool_selection_provider_quality,
    render_intent_provider_report,
    render_tool_selection_provider_report,
)
from app.evals.career_tool_selection import load_career_tool_selection_eval_dataset
from app.llm.career_intent_models import (
    CareerIntentModelBlockedError,
    CareerIntentModelFailedError,
    CareerIntentModelOutputError,
    DisabledCareerIntentModel,
    build_career_intent_model,
)


class _FakeProviderModel:
    """Offline stand-in with explicit payloads, counters and optional failure."""

    def __init__(
        self,
        *,
        payloads: dict[str, dict[str, object]],
        model_name: str = "fake-model",
        failure: Exception | None = None,
        malformed_messages: tuple[str, ...] = (),
    ) -> None:
        self._payloads = payloads
        self._model_name = model_name
        self._failure = failure
        self._malformed_messages = set(malformed_messages)
        self._attempts = 0
        self._completed = 0

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def attempts(self) -> int:
        return self._attempts

    @property
    def completed(self) -> int:
        return self._completed

    def route(self, user_message: str) -> dict[str, object]:
        if self._failure is not None:
            self._attempts += 1
            raise self._failure
        if user_message in self._malformed_messages:
            self._attempts += 1
            raise CareerIntentModelOutputError("payload violated contract")
        self._attempts += 1
        self._completed += 1
        return dict(self._payloads[user_message])


def _payload_for(case: IntentEvalCase) -> dict[str, object]:
    """Build the payload a perfectly correct model would return.

    Only the cases that carry ``clarificationQuestionContains`` require the model
    to author clarification wording.  For a pronoun reference the correct model
    output is ``current_job_required = True`` with no clarification flag, because
    the Core resolver owns the "no governed current job" fallback.  Setting the
    flag here instead would be the model overstepping its contract.
    """

    expected = case.expected
    model_owned_clarification = expected.clarification_question_contains is not None
    return {
        "goals": list(expected.goals),
        "referenced_job_ids": list(expected.referenced_job_ids),
        "current_job_required": expected.current_job_required,
        "needs_clarification": expected.needs_clarification
        and model_owned_clarification,
        "clarification_question": (
            f"Please clarify which {expected.clarification_question_contains} you mean"
            if model_owned_clarification
            else None
        ),
        "unsupported_request": (
            "outside scope" if expected.unsupported_request is not None else None
        ),
        "confidence": None,
        "reasoning_summary": "fixture",
    }


def _corrupted_intent_model(
    cases: tuple[IntentEvalCase, ...], *, wrong: int
) -> _FakeProviderModel:
    """Return a model that answers the first ``wrong`` cases incorrectly."""

    payloads = {case.message: _payload_for(case) for case in cases}
    for case in cases[:wrong]:
        payloads[case.message] = {**_payload_for(case), "goals": ["unknown"]}
    return _FakeProviderModel(payloads=payloads)


def _perfect_intent_model(
    cases: tuple[IntentEvalCase, ...],
) -> _FakeProviderModel:
    return _FakeProviderModel(
        payloads={case.message: _payload_for(case) for case in cases}
    )


# --------------------------------------------------------------------------- #
# Disabled provider must never look like a pass
# --------------------------------------------------------------------------- #


def test_factory_defaults_to_disabled() -> None:
    model = build_career_intent_model(Settings(_env_file=None))

    assert isinstance(model, DisabledCareerIntentModel)
    assert model.model_name == "disabled"


def test_disabled_provider_reports_not_measured_for_intent() -> None:
    report = measure_career_intent_provider_quality(model=DisabledCareerIntentModel())

    assert report.status is ProviderGateStatus.NOT_MEASURED
    assert report.status is not ProviderGateStatus.PASS
    assert report.accuracy_met is False
    assert report.provider_attempts == 0
    assert report.provider_completed == 0
    assert report.case_results == ()


def test_disabled_provider_reports_not_measured_for_tool_selection() -> None:
    report = measure_career_tool_selection_provider_quality(
        model=DisabledCareerIntentModel()
    )

    assert report.status is ProviderGateStatus.NOT_MEASURED
    assert report.accuracy_met is False
    assert report.provider_attempts == 0
    assert report.case_results == ()


# --------------------------------------------------------------------------- #
# Intent gate measurement
# --------------------------------------------------------------------------- #


def test_perfect_model_scores_full_accuracy_and_passes() -> None:
    cases = load_career_intent_eval_dataset()
    model = _perfect_intent_model(cases)

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    assert report.total_cases == 60
    assert report.exact_matches == 60
    assert report.exact_accuracy == 1.0
    assert report.acceptable_accuracy == 1.0
    assert report.status is ProviderGateStatus.PASS
    assert report.bad_cases == ()


def test_gate_does_not_fail_because_a_provider_was_used() -> None:
    """The B gate exists to use the provider; usage is an observation."""

    cases = load_career_intent_eval_dataset()
    model = _perfect_intent_model(cases)

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    assert report.provider_attempts == 60
    assert report.provider_completed == 60
    assert report.business_writes == 0
    assert report.status is ProviderGateStatus.PASS


def test_gate_records_bad_cases_with_expected_and_actual_goals() -> None:
    cases = load_career_intent_eval_dataset()
    target = cases[0]
    model = _corrupted_intent_model(cases, wrong=1)

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    assert report.exact_matches == 59
    assert [result.case_id for result in report.bad_cases] == [target.case_id]
    bad = report.bad_cases[0]
    assert bad.actual_goals == ("unknown",)
    assert bad.expected_goals == target.expected.goals


def test_one_miss_in_sixty_still_meets_the_prd_tolerance() -> None:
    """58/60 is 98.3%, so the PRD 95% bar is a floor, not a perfect-score rule."""

    cases = load_career_intent_eval_dataset()
    model = _corrupted_intent_model(cases, wrong=1)

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    assert report.exact_accuracy == pytest.approx(59 / 60)
    assert report.accuracy_met is True
    assert report.status is ProviderGateStatus.PASS


def test_gate_fails_once_accuracy_falls_below_the_threshold() -> None:
    cases = load_career_intent_eval_dataset()
    model = _corrupted_intent_model(cases, wrong=4)

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    assert report.exact_matches == 56
    assert report.exact_accuracy < GATE_MINIMUM_ACCURACY
    assert report.accuracy_met is False
    assert report.status is ProviderGateStatus.FAIL
    assert len(report.bad_cases) == 4


def test_gate_counts_unsafe_auto_execution_as_a_safety_violation() -> None:
    """An unsafe request routed to a real goal is the worst possible outcome."""

    cases = load_career_intent_eval_dataset()
    unsafe = tuple(
        case for case in cases if case.expected.unsupported_request is not None
    )
    assert unsafe, "cohort must contain unsupported_unsafe cases"
    target = unsafe[0]
    payloads = {case.message: _payload_for(case) for case in cases}
    payloads[target.message] = {
        **_payload_for(target),
        "goals": ["rank_jobs"],
        "unsupported_request": None,
    }
    model = _FakeProviderModel(payloads=payloads)

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    assert report.unsafe_auto_executions == 1
    assert report.safety_met is False
    assert report.status is ProviderGateStatus.FAIL


def test_gate_counts_clarification_execution_as_a_safety_violation() -> None:
    cases = load_career_intent_eval_dataset()
    clarify = tuple(
        case
        for case in cases
        if case.expected.needs_clarification
        and not case.expected.current_job_required
    )
    assert clarify, "cohort must contain model-owned clarification cases"
    target = clarify[0]
    payloads = {case.message: _payload_for(case) for case in cases}
    payloads[target.message] = {
        **_payload_for(target),
        "goals": ["rank_jobs"],
        "needs_clarification": False,
        "clarification_question": None,
    }
    model = _FakeProviderModel(payloads=payloads)

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    assert report.clarification_executions == 1
    assert report.safety_met is False
    assert report.status is ProviderGateStatus.FAIL


def test_gate_detects_out_of_scope_reference_from_the_raw_payload() -> None:
    cases = load_career_intent_eval_dataset()
    scoped = tuple(case for case in cases if case.context.run_job_ids)
    target = scoped[0]
    payloads = {case.message: _payload_for(case) for case in cases}
    payloads[target.message] = {
        **_payload_for(target),
        "referenced_job_ids": ["job-999999"],
    }
    model = _FakeProviderModel(payloads=payloads)

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    assert report.out_of_scope_references == 1
    assert report.safety_met is False
    assert report.status is ProviderGateStatus.FAIL


def test_malformed_output_is_fail_closed_and_counted_separately() -> None:
    cases = load_career_intent_eval_dataset()
    target = cases[0]
    payloads = {case.message: _payload_for(case) for case in cases}
    model = _FakeProviderModel(
        payloads=payloads, malformed_messages=(target.message,)
    )

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    result = next(r for r in report.case_results if r.case_id == target.case_id)
    assert result.failure_kind == "malformed_output"
    assert result.exact is False
    assert report.malformed_outputs == 1
    # Fail-closed means no goal was ever produced for that turn.
    assert result.actual_goals == ()
    assert report.safety_met is True


def test_transport_failure_is_bounded_and_never_executed() -> None:
    cases = load_career_intent_eval_dataset()
    model = _FakeProviderModel(
        payloads={}, failure=CareerIntentModelFailedError("provider unreachable")
    )

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    assert report.transport_failures == 60
    assert report.exact_matches == 0
    assert report.status is ProviderGateStatus.FAIL
    assert report.business_writes == 0


def test_minimum_accuracy_threshold_is_the_prd_value() -> None:
    assert GATE_MINIMUM_ACCURACY == 0.95


# --------------------------------------------------------------------------- #
# Provider-level refusals must abort instead of burning the whole cohort
# --------------------------------------------------------------------------- #


class _BlockedProviderModel:
    """Model that refuses for a reason retrying cannot fix."""

    def __init__(self) -> None:
        self._attempts = 0

    @property
    def model_name(self) -> str:
        return "blocked-model"

    @property
    def attempts(self) -> int:
        return self._attempts

    @property
    def completed(self) -> int:
        return 0

    def route(self, user_message: str) -> dict[str, object]:  # noqa: ARG002
        self._attempts += 1
        raise CareerIntentModelBlockedError(
            "intent provider refused the request in a way retrying cannot fix: "
            "HTTPStatusError(status=402 code=INSUFFICIENT_BALANCE)"
        )


def test_billing_refusal_aborts_the_run_instead_of_repeating_per_case() -> None:
    cases = load_career_intent_eval_dataset()
    model = _BlockedProviderModel()

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    assert report.status is ProviderGateStatus.NOT_MEASURED
    assert report.provider_attempts == 1
    assert report.case_results == ()
    assert report.blocked_reason is not None
    assert "402" in report.blocked_reason
    assert "INSUFFICIENT_BALANCE" in report.blocked_reason
    assert report.exact_accuracy == 0.0
    assert report.status is not ProviderGateStatus.PASS


def test_tool_selection_gate_also_aborts_on_a_provider_refusal() -> None:
    model = _BlockedProviderModel()

    report = measure_career_tool_selection_provider_quality(model=model)

    assert report.status is ProviderGateStatus.NOT_MEASURED
    assert report.provider_attempts == 1
    assert report.workflow_invocations == 0


def test_http_402_is_not_retried_by_the_model_transport() -> None:
    """A 402 is raised immediately; retrying an unfunded account is pointless."""

    import httpx

    from app.llm.career_intent_models import OpenAICareerIntentModel

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            402,
            json={
                "code": "INSUFFICIENT_BALANCE",
                "message": "no balance",
                "traceId": "trace_test",
            },
        )

    model = OpenAICareerIntentModel(
        api_key="test-key",
        model="test-model",
        max_http_attempts=3,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(CareerIntentModelBlockedError) as error:
        model.route("Rank my jobs.")

    assert len(seen) == 1, "a billing refusal must not be retried"
    assert model.attempts == 1
    assert model.completed == 0
    assert "402" in str(error.value)
    assert "INSUFFICIENT_BALANCE" in str(error.value)


def test_rendered_intent_report_states_status_and_bad_cases() -> None:
    cases = load_career_intent_eval_dataset()
    target = cases[0]
    model = _corrupted_intent_model(cases, wrong=4)

    text = render_intent_provider_report(
        measure_career_intent_provider_quality(model=model, cases=cases)
    )

    assert "Intent Provider Gate: FAIL" in text
    assert target.case_id in text
    assert "fake-model" in text


# --------------------------------------------------------------------------- #
# Tool selection gate
# --------------------------------------------------------------------------- #


def _perfect_tool_model() -> _FakeProviderModel:
    cases = load_career_tool_selection_eval_dataset()
    return _FakeProviderModel(
        payloads={case.message: dict(case.intent_payload) for case in cases}
    )


def test_tool_selection_gate_replays_frozen_intents_without_executing() -> None:
    report = measure_career_tool_selection_provider_quality(
        model=_perfect_tool_model()
    )

    assert report.total_cases == 44
    assert report.exact_matches == 44
    assert report.exact_accuracy == 1.0
    assert report.status is ProviderGateStatus.PASS
    # Selection alone must never reach a business workflow.
    assert report.workflow_invocations == 0
    assert report.business_writes == 0


def test_tool_selection_gate_counts_forbidden_tool_selection() -> None:
    cases = load_career_tool_selection_eval_dataset()
    payloads = {case.message: dict(case.intent_payload) for case in cases}
    forbidden = next(case for case in cases if case.category.value == "forbidden_tool")
    payloads[forbidden.message] = {
        **dict(forbidden.intent_payload),
        "goals": ["rank_jobs"],
    }
    model = _FakeProviderModel(payloads=payloads)

    report = measure_career_tool_selection_provider_quality(model=model, cases=cases)

    assert report.forbidden_tool_selections == 1
    assert report.safety_met is False
    assert report.status is ProviderGateStatus.FAIL
    assert report.workflow_invocations == 0


def test_tool_selection_gate_counts_out_of_scope_selection() -> None:
    cases = load_career_tool_selection_eval_dataset()
    payloads = {case.message: dict(case.intent_payload) for case in cases}
    scoped = next(
        case for case in cases if case.category.value == "wrong_job_scope"
    )
    payloads[scoped.message] = {
        **dict(scoped.intent_payload),
        "referenced_job_ids": [],
    }
    model = _FakeProviderModel(payloads=payloads)

    report = measure_career_tool_selection_provider_quality(model=model, cases=cases)

    assert report.out_of_scope_selections == 1
    assert report.safety_met is False
    assert report.status is ProviderGateStatus.FAIL


def test_rendered_tool_report_states_status() -> None:
    text = render_tool_selection_provider_report(
        measure_career_tool_selection_provider_quality(model=_perfect_tool_model())
    )

    assert "Tool Selection Provider Gate: PASS" in text
    assert "workflow_invocations=0" in text
