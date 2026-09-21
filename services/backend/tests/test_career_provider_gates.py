"""Tests for the provider-authorized model-quality gates.

These tests never contact a Provider.  They prove that the gate plumbing measures
what it claims to measure, that every safety counter is wired to a real signal,
and — most importantly — that a disabled Provider can never be reported as a pass.
"""
from __future__ import annotations

import json

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


# --------------------------------------------------------------------------- #
# Transport success path
#
# The live endpoint was unfunded while these gates were built, so the request
# shape and the parsing of a real 200 response are pinned here against a mock
# transport instead of being left to the first paid run.
# --------------------------------------------------------------------------- #


_VALID_PAYLOAD = {
    "goals": ["rank_jobs"],
    "referenced_job_ids": [],
    "current_job_required": False,
    "needs_clarification": False,
    "clarification_question": None,
    "unsupported_request": None,
    "confidence": 0.9,
    "reasoning_summary": "The user asks to compare jobs.",
}


def _chat_completion_200(payload: object, *, content: str | None = None) -> dict:
    return {
        "id": "chatcmpl-test",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": (
                        content if content is not None else json.dumps(payload)
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }


def _capturing_model(responses: list["httpx.Response"], **model_kwargs: object):
    import httpx

    from app.llm.career_intent_models import OpenAICareerIntentModel

    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            {"url": str(request.url), "body": json.loads(request.content)}
        )
        return responses[min(len(requests) - 1, len(responses) - 1)]

    model = OpenAICareerIntentModel(
        api_key="test-key",
        model="test-model",
        base_url="https://example.test/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        **model_kwargs,  # type: ignore[arg-type]
    )
    return model, requests


def test_chat_completions_request_shape_matches_the_verified_probe() -> None:
    """Mirror the shape a health check already proved this endpoint accepts."""

    import httpx

    model, requests = _capturing_model(
        [httpx.Response(200, json=_chat_completion_200(_VALID_PAYLOAD))]
    )

    model.route("Rank my jobs.")

    body = requests[0]["body"]
    assert requests[0]["url"] == "https://example.test/v1/chat/completions"
    assert body["model"] == "test-model"
    assert body["stream"] is False
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"]["type"] == "object"
    # An unproven field must not be sent: the verified probe omits it.
    assert "temperature" not in body
    assert isinstance(body["messages"], list)
    assert body["messages"][-1]["content"] == "Rank my jobs."


def test_http_200_payload_is_parsed_and_counted() -> None:
    import httpx

    model, _ = _capturing_model(
        [httpx.Response(200, json=_chat_completion_200(_VALID_PAYLOAD))]
    )

    payload = model.route("Rank my jobs.")

    assert payload["goals"] == ["rank_jobs"]
    assert payload["confidence"] == 0.9
    assert model.attempts == 1
    assert model.completed == 1


def test_http_200_with_unparseable_content_fails_closed() -> None:
    import httpx

    model, _ = _capturing_model(
        [httpx.Response(200, json=_chat_completion_200(None, content="not json"))]
    )

    with pytest.raises(CareerIntentModelOutputError):
        model.route("Rank my jobs.")

    assert model.attempts == 1
    assert model.completed == 0


def test_schema_violation_is_not_retried() -> None:
    """A payload that violates the contract is a model fact, not a flake."""

    import httpx

    model, requests = _capturing_model(
        [
            httpx.Response(
                200,
                json=_chat_completion_200({**_VALID_PAYLOAD, "unexpected_field": 1}),
            )
        ]
    )

    with pytest.raises(CareerIntentModelOutputError):
        model.route("Rank my jobs.")

    assert len(requests) == 1, "a contract violation must not be retried"
    assert model.attempts == 1
    assert model.completed == 0


def test_transient_http_error_is_retried_then_succeeds() -> None:
    import httpx

    model, requests = _capturing_model(
        [
            httpx.Response(500, json={"error": "temporary"}),
            httpx.Response(200, json=_chat_completion_200(_VALID_PAYLOAD)),
        ]
    )

    payload = model.route("Rank my jobs.")

    assert payload["goals"] == ["rank_jobs"]
    assert len(requests) == 2
    # Two attempts, one parseable payload: the counters keep them distinct.
    assert model.attempts == 2
    assert model.completed == 1


def test_responses_api_style_parses_output_text() -> None:
    import httpx

    from app.llm.career_intent_models import OpenAICareerIntentModel

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/responses")
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps(_VALID_PAYLOAD)}
                        ],
                    }
                ]
            },
        )

    model = OpenAICareerIntentModel(
        api_key="test-key",
        model="test-model",
        base_url="https://example.test/v1",
        api_style="responses",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    payload = model.route("Rank my jobs.")

    assert payload["goals"] == ["rank_jobs"]
    assert model.attempts == 1
    assert model.completed == 1


def test_rate_limit_is_honoured_rather_than_treated_as_a_failure() -> None:
    """A 429 tells us when to come back; that is not a transport failure."""

    import httpx

    sleeps: list[float] = []
    model, requests = _capturing_model(
        [
            httpx.Response(
                429,
                json={
                    "code": "RATE_LIMITED",
                    "message": "too many requests",
                    "data": {"limit": 20, "retryAfterSeconds": 7},
                },
            ),
            httpx.Response(200, json=_chat_completion_200(_VALID_PAYLOAD)),
        ],
        sleep=sleeps.append,
    )

    payload = model.route("Rank my jobs.")

    assert payload["goals"] == ["rank_jobs"]
    assert len(requests) == 2
    assert model.attempts == 2
    assert model.completed == 1
    assert model.rate_limited == 1
    assert sleeps == [7.0], "the provider's own retryAfterSeconds must be honoured"


def test_rate_limit_without_a_hint_uses_a_bounded_default() -> None:
    import httpx

    sleeps: list[float] = []
    model, _ = _capturing_model(
        [
            httpx.Response(429, json={"code": "RATE_LIMITED"}),
            httpx.Response(200, json=_chat_completion_200(_VALID_PAYLOAD)),
        ],
        sleep=sleeps.append,
    )

    model.route("Rank my jobs.")

    assert len(sleeps) == 1
    assert 0 < sleeps[0] <= 120.0


def test_persistent_rate_limiting_fails_closed_after_bounded_retries() -> None:
    import httpx

    sleeps: list[float] = []
    model, requests = _capturing_model(
        [httpx.Response(429, json={"code": "RATE_LIMITED", "data": {"retryAfterSeconds": 1}})],
        max_rate_limit_retries=2,
        sleep=sleeps.append,
    )

    with pytest.raises(CareerIntentModelFailedError):
        model.route("Rank my jobs.")

    # Two honoured 429 waits, then the general transport budget is consumed.
    assert len(sleeps) == 2
    assert model.rate_limited == 2
    assert model.completed == 0
    assert len(requests) > 2


def test_pacing_enforces_a_minimum_interval_between_calls() -> None:
    import httpx

    sleeps: list[float] = []
    model, requests = _capturing_model(
        [httpx.Response(200, json=_chat_completion_200(_VALID_PAYLOAD))],
        min_request_interval_seconds=3.0,
        sleep=sleeps.append,
    )

    model.route("Rank my jobs.")
    model.route("Rank my jobs.")

    assert len(requests) == 2
    # The first call has nothing to wait for; the second must respect the pace.
    assert len(sleeps) == 1
    assert 0 < sleeps[0] <= 3.0


def test_end_to_end_gate_runs_over_a_mocked_transport() -> None:
    """Prove the whole gate walks NL -> HTTP -> Core router on a real payload."""

    import httpx

    from app.llm.career_intent_models import OpenAICareerIntentModel

    cases = load_career_intent_eval_dataset()
    by_message = {case.message: _payload_for(case) for case in cases}

    def handler(request: httpx.Request) -> httpx.Response:
        message = json.loads(request.content)["messages"][-1]["content"]
        return httpx.Response(200, json=_chat_completion_200(by_message[message]))

    model = OpenAICareerIntentModel(
        api_key="test-key",
        model="test-model",
        base_url="https://example.test/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    report = measure_career_intent_provider_quality(model=model, cases=cases)

    assert report.total_cases == 60
    assert report.exact_matches == 60
    assert report.status is ProviderGateStatus.PASS
    assert report.provider_attempts == 60
    assert report.provider_completed == 60


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


# --------------------------------------------------------------------------- #
# Operable entry point
# --------------------------------------------------------------------------- #


def test_cli_never_contacts_a_provider_without_both_flags() -> None:
    from scripts.check_career_provider_gates import run_career_provider_gates

    result = run_career_provider_gates(
        settings=Settings(_env_file=None),
        execute_provider_gate=False,
        confirm_live_cost=False,
    )

    assert result.provider_calls == 0
    assert result.execution_requested is False
    assert result.intent.status is ProviderGateStatus.NOT_MEASURED
    assert result.tool_selection.status is ProviderGateStatus.NOT_MEASURED


def test_cli_requires_the_cost_flag_even_when_execution_was_requested() -> None:
    from scripts.check_career_provider_gates import run_career_provider_gates

    result = run_career_provider_gates(
        settings=Settings(_env_file=None),
        execute_provider_gate=True,
        confirm_live_cost=False,
    )

    assert result.provider_calls == 0
    assert result.intent.status is ProviderGateStatus.NOT_MEASURED


def test_exit_code_separates_blocked_from_failed() -> None:
    from dataclasses import replace

    from scripts.check_career_provider_gates import (
        career_provider_gate_exit_code,
        run_career_provider_gates,
    )

    result = run_career_provider_gates(
        settings=Settings(_env_file=None),
        execute_provider_gate=False,
        confirm_live_cost=False,
    )
    assert career_provider_gate_exit_code(result) == 2

    failed = replace(result, intent=replace(result.intent, status=ProviderGateStatus.FAIL))
    assert career_provider_gate_exit_code(failed) == 1

    passed = replace(
        failed,
        intent=replace(result.intent, status=ProviderGateStatus.PASS),
        tool_selection=replace(
            result.tool_selection, status=ProviderGateStatus.PASS
        ),
    )
    assert career_provider_gate_exit_code(passed) == 0


def test_snapshot_path_stays_inside_the_ignored_local_directory() -> None:
    """A hand-computed path here once landed in a tracked directory."""

    from app.evals.provider_smoke import DEFAULT_PROVIDER_SMOKE_SNAPSHOT
    from scripts.check_career_provider_gates import DEFAULT_SNAPSHOT_PATH

    assert DEFAULT_SNAPSHOT_PATH.parent == DEFAULT_PROVIDER_SMOKE_SNAPSHOT.parent
    assert DEFAULT_SNAPSHOT_PATH.parent.name == "local"
    assert DEFAULT_SNAPSHOT_PATH.name == "career-provider-gates.json"


def test_snapshot_is_camel_case_and_carries_no_credentials(tmp_path) -> None:
    from scripts.check_career_provider_gates import (
        run_career_provider_gates,
        save_career_provider_gate_snapshot,
    )

    settings = Settings(
        _env_file=None,
        career_intent_provider="openai",
        career_intent_model="secret-model-name",
        openai_api_key="sk-super-secret-value",
        openai_base_url="https://secret.example.test/v1",
    )
    result = run_career_provider_gates(
        settings=settings,
        execute_provider_gate=False,
        confirm_live_cost=False,
    )
    path = tmp_path / "snapshot.json"
    save_career_provider_gate_snapshot(result, path=path)

    text = path.read_text(encoding="utf-8")
    assert "sk-super-secret-value" not in text
    assert "secret.example.test" not in text
    parsed = json.loads(text)
    assert parsed["checkedAt"]
    assert "providerCalls" in parsed
    assert "promptVersion" in parsed
    assert "toolSelection" in parsed
    assert parsed["intent"]["status"] == "not_measured"
    assert parsed["intent"]["exactAccuracy"] == 0.0
