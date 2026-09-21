"""Provider adapters for the governed Career Agent intent seam.

These adapters implement only the transport boundary of ``CareerIntentModel``:
they turn one user message into one strict JSON payload.  They deliberately do
not resolve job references, do not decide execution order beyond the model's own
goal ordering, and do not implement a second Router, Tool Registry or runtime.
Grounding, scope enforcement and clarification fallback stay in
``app.agent.intent.CareerIntentRouter``.
"""
from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.intent import CareerIntentGoal
from app.core.config import Settings

#: Bump whenever the intent prompt or the structured output schema changes, so a
#: measured accuracy number can always be traced back to the exact input it saw.
CAREER_INTENT_PROMPT_VERSION = "career-intent-prompt-v1"
CAREER_INTENT_SCHEMA_VERSION = "career-intent-schema-v1"


class CareerIntentModelUnavailableError(RuntimeError):
    """Raised when no intent provider is configured for a real model call."""


class CareerIntentModelFailedError(RuntimeError):
    """Raised when the provider call or its payload cannot be trusted."""


class CareerIntentModelOutputError(CareerIntentModelFailedError):
    """Raised when the provider replied but the payload violated the contract.

    Kept as a distinct subclass because "the model produced malformed output" and
    "the transport failed" are different quality facts and must be counted
    separately by the provider gate.
    """


class CareerIntentModelBlockedError(CareerIntentModelFailedError):
    """Raised when the provider refuses for a reason retrying cannot fix.

    Authentication and billing refusals belong here.  Retrying an unfunded account
    once per case would spend an entire cohort's worth of calls to learn a fact a
    single call already established, so this is surfaced immediately and the gate
    reports ``NOT_MEASURED`` with the provider code instead of a fake accuracy.
    """


#: HTTP statuses where retrying the same request cannot succeed.
_NON_RETRYABLE_STATUSES = frozenset({401, 402, 403})


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _IntentOutput(_StrictModel):
    """Mirror of the exact payload ``CareerIntentRouter`` accepts."""

    goals: list[CareerIntentGoal]
    referenced_job_ids: list[str]
    current_job_required: bool
    needs_clarification: bool
    clarification_question: str | None
    unsupported_request: str | None
    confidence: float | None
    reasoning_summary: str = Field(max_length=500)


class DisabledCareerIntentModel:
    """Default adapter: refuses loudly instead of guessing an intent."""

    def __init__(self) -> None:
        self._attempts = 0
        self._completed = 0

    @property
    def model_name(self) -> str:
        return "disabled"

    @property
    def attempts(self) -> int:
        return self._attempts

    @property
    def completed(self) -> int:
        return self._completed

    def route(self, user_message: str) -> dict[str, object]:
        raise CareerIntentModelUnavailableError(
            "Career intent model is disabled. Configure CAREER_INTENT_PROVIDER."
        )


class OpenAICareerIntentModel:
    """OpenAI-compatible intent adapter using strict JSON Schema output.

    ``attempts`` counts HTTP calls and ``completed`` counts validated payloads, so
    a retry is visible as attempts > completed for the same turn.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        api_style: Literal["responses", "chat_completions"] = "chat_completions",
        enable_thinking: bool | None = None,
        max_completion_tokens: int | None = None,
        timeout_seconds: float = 60.0,
        max_http_attempts: int = 2,
        temperature: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        """Configure the adapter.

        ``temperature`` defaults to ``None`` so the field is omitted entirely.
        Every provider adapter in this repository that has been verified healthy
        against the configured endpoint omits it, and sending an unproven field
        would trade a proven request shape for an untested one.  Pass an explicit
        value only after confirming the endpoint accepts it.
        """

        self._api_key = api_key
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._api_style = api_style.strip().casefold()
        self._enable_thinking = enable_thinking
        self._max_completion_tokens = max_completion_tokens
        self._timeout_seconds = timeout_seconds
        self._max_http_attempts = max(1, max_http_attempts)
        self._temperature = temperature
        self._client = client
        self._attempts = 0
        self._completed = 0

    @property
    def model_name(self) -> str:
        return self._model or "openai-unconfigured"

    @property
    def attempts(self) -> int:
        return self._attempts

    @property
    def completed(self) -> int:
        return self._completed

    def route(self, user_message: str) -> dict[str, object]:
        if not self._api_key or not self._model:
            raise CareerIntentModelUnavailableError(
                "OpenAI career intent model requires OPENAI_API_KEY and "
                "CAREER_INTENT_MODEL."
            )
        message = user_message.strip()
        if not message:
            raise CareerIntentModelOutputError("intent message must not be blank")

        schema = _IntentOutput.model_json_schema()
        if self._api_style == "responses":
            request_url = f"{self._base_url}/responses"
            request_body: dict[str, Any] = {
                "model": self._model,
                "store": False,
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": message}],
                    },
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": CAREER_INTENT_SCHEMA_VERSION,
                        "description": "Governed career intent routing payload",
                        "strict": True,
                        "schema": schema,
                    }
                },
            }
            output_text = _response_output_text
        elif self._api_style == "chat_completions":
            request_url = f"{self._base_url}/chat/completions"
            request_body = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
                "stream": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": CAREER_INTENT_SCHEMA_VERSION,
                        "description": "Governed career intent routing payload",
                        "strict": True,
                        "schema": schema,
                    },
                },
            }
            if self._enable_thinking is not None:
                request_body["enable_thinking"] = self._enable_thinking
            if self._max_completion_tokens is not None:
                request_body["max_completion_tokens"] = self._max_completion_tokens
            if self._temperature is not None:
                request_body["temperature"] = self._temperature
            output_text = _chat_completion_output_text
        else:
            raise CareerIntentModelUnavailableError(
                "Career intent API style must be responses or chat_completions."
            )

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for _ in range(self._max_http_attempts):
            self._attempts += 1
            try:
                payload = self._post(
                    request_url=request_url, headers=headers, request_body=request_body
                )
            except (httpx.HTTPStatusError, httpx.HTTPError, json.JSONDecodeError) as error:
                if (
                    isinstance(error, httpx.HTTPStatusError)
                    and error.response.status_code in _NON_RETRYABLE_STATUSES
                ):
                    code, trace_id = _provider_error_identity(error.response)
                    suffix = f" code={code}" if code else ""
                    suffix += f" traceId={trace_id}" if trace_id else ""
                    raise CareerIntentModelBlockedError(
                        "intent provider refused the request in a way retrying cannot "
                        f"fix: HTTPStatusError(status={error.response.status_code}{suffix})"
                    ) from error
                # Transport-level problems are the only retryable class. A payload
                # that arrived but violated the contract is never retried, because
                # retrying it would hide a model-quality failure.
                last_error = error
                continue

            try:
                parsed = _IntentOutput.model_validate_json(output_text(payload))
            except (ValidationError, KeyError, ValueError, TypeError) as error:
                raise CareerIntentModelOutputError(
                    f"intent payload violated contract: {type(error).__name__}: {error}"
                ) from error

            self._completed += 1
            return parsed.model_dump(mode="json")

        raise CareerIntentModelFailedError(
            f"intent provider call failed after {self._attempts} attempt(s): "
            f"{_describe_transport_error(last_error)}"
        ) from last_error

    def _post(
        self,
        *,
        request_url: str,
        headers: dict[str, str],
        request_body: dict[str, Any],
    ) -> Any:
        if self._client is not None:
            response = self._client.post(request_url, headers=headers, json=request_body)
        else:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(request_url, headers=headers, json=request_body)
        response.raise_for_status()
        return response.json()


def _response_output_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise CareerIntentModelOutputError("response must be a JSON object")
    for item in _iter_dicts(payload.get("output")):
        if item.get("type") != "message":
            continue
        for content in _iter_dicts(item.get("content")):
            if content.get("type") == "refusal":
                raise CareerIntentModelOutputError("provider refused intent routing")
            if content.get("type") == "output_text" and isinstance(
                content.get("text"), str
            ):
                return content["text"]
    raise CareerIntentModelOutputError("response contained no output_text")


def _chat_completion_output_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise CareerIntentModelOutputError("chat response must be a JSON object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise CareerIntentModelOutputError("chat response contained no choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise CareerIntentModelOutputError("chat choice must be a JSON object")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise CareerIntentModelOutputError("chat response contained no message")
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal:
        raise CareerIntentModelOutputError("provider refused intent routing")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    for item in _iter_dicts(content):
        if item.get("type") == "refusal":
            raise CareerIntentModelOutputError("provider refused intent routing")
        if item.get("type") in {"text", "output_text"} and isinstance(
            item.get("text"), str
        ):
            return item["text"]
    raise CareerIntentModelOutputError("chat response contained no text content")


def _iter_dicts(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _describe_transport_error(error: Exception | None) -> str:
    """Render a provider failure with the fields an operator needs to act on.

    A bare exception class name hides the difference between "the account has no
    balance" and "the request shape was rejected", which are completely different
    operator actions.  The provider code and trace id are surfaced without ever
    echoing response bodies that could contain model output.
    """

    if error is None:
        return "no attempt was made"
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        code, trace_id = _provider_error_identity(response)
        suffix = f" code={code}" if code else ""
        suffix += f" traceId={trace_id}" if trace_id else ""
        return f"HTTPStatusError(status={response.status_code}{suffix})"
    return f"{type(error).__name__}"


def _provider_error_identity(response: httpx.Response) -> tuple[str | None, str | None]:
    trace_id = None
    for header in ("x-trace-id", "trace-id"):
        value = response.headers.get(header)
        if value and value.strip():
            trace_id = value.strip()[:128]
            break
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, trace_id
    if not isinstance(payload, dict):
        return None, trace_id
    code = payload.get("code")
    code = code.strip()[:64] if isinstance(code, str) and code.strip() else None
    if trace_id is None:
        value = payload.get("traceId")
        trace_id = value.strip()[:128] if isinstance(value, str) and value.strip() else None
    return code, trace_id


def build_career_intent_model(settings: Settings) -> Any:
    """Runtime factory for the configured career intent adapter.

    Defaults to ``disabled`` so a missing configuration can never silently issue
    real provider calls.  Enabling it is an explicit, human-authorized act.
    """

    provider = settings.career_intent_provider.strip().casefold()
    if provider == "openai":
        return OpenAICareerIntentModel(
            api_key=settings.openai_api_key,
            model=settings.career_intent_model,
            base_url=settings.openai_base_url,
            api_style=settings.career_intent_api_style,
            enable_thinking=settings.career_intent_enable_thinking,
            max_completion_tokens=settings.career_intent_max_completion_tokens,
            timeout_seconds=settings.career_intent_timeout_seconds,
        )
    return DisabledCareerIntentModel()


SYSTEM_PROMPT = """Route one career-assistant user message into a governed intent payload.

You only classify and extract. You do not execute anything and you do not see any
job database, so never invent an identifier you were not given.

Goals (use only these exact values):
- rank_jobs: compare, sort, prioritise or choose among several jobs.
- review_gaps: identify missing skills, gaps, or what the user lacks.
- prepare_job: build interview preparation, focus areas, or readiness steps.
- review_application: inspect application evidence or application readiness.
- unknown: the request maps to no supported goal.

Ordering:
- List goals in the order the user wants them executed.
- When the user asks for several things and states an order (for example "first
  ... then ..."), follow that order. Otherwise use the natural order implied by
  the sentence.
- Never repeat a goal.

referenced_job_ids:
- Copy identifiers that appear literally in the user message, in the form
  job-<digits>. Copy them exactly, in the order they appear, and deduplicate.
- Never guess, never complete, never translate a job title into an identifier.

current_job_required:
- true when the user points at one job by pronoun or demonstrative instead of
  naming it, for example "this job", "this role", "this one", "this opening",
  "this position", "this application".
- Leave referenced_job_ids empty in that case; the caller supplies the identity.
- false otherwise.

needs_clarification:
- true when the request cannot be safely executed as stated: it is too vague to
  map to any goal, it could refer to several different jobs, or it relies on a
  set of jobs that is not defined by the conversation.
- When true, write clarification_question as one short question that names what
  is missing, and put no executable goal in goals.
- Prefer clarification over guessing. Asking is always safer than a wrong action.

unsupported_request:
- Set to a short explanation when the user asks for something outside career
  analysis, for example salary negotiation guarantees, legal advice, or anything
  that would need data or actions this assistant does not have.
- When set, goals must be empty or contain only unknown.

reasoning_summary: one sentence, at most 500 characters, stating why you chose
these goals. Never include personal data beyond what the user wrote.
"""
