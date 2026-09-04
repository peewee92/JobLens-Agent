"""Job Requirement Extractor adapters for disabled, fixture and OpenAI providers."""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable
from typing import Annotated, Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.application.job_requirements import (
    JobRequirementExtractionOutput,
    JobRequirementExtractorResult,
    ProposedJobRequirement,
    RequirementExtractorFailedError,
    RequirementExtractorUnavailableError,
)
from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
from app.domain.job_requirements import RequirementImportance, RequirementType


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _RequirementOutputBase(_StrictModel):
    original_text: str = Field(alias="originalText", min_length=1, max_length=4000)
    source_candidate_id: str = Field(alias="sourceCandidateId", min_length=5, max_length=16)
    importance: RequirementImportance
    confidence: float = Field(ge=0, le=1)


class _SkillRequirementOutput(_RequirementOutputBase):
    type: Literal[RequirementType.SKILL]
    normalized_capability: str = Field(
        alias="normalizedCapability",
        min_length=1,
        max_length=255,
    )


class _OtherRequirementOutput(_RequirementOutputBase):
    type: Literal[
        RequirementType.EXPERIENCE,
        RequirementType.EDUCATION,
        RequirementType.RESPONSIBILITY,
        RequirementType.DOMAIN,
        RequirementType.CONSTRAINT,
    ]
    normalized_capability: str | None = Field(
        alias="normalizedCapability",
        max_length=255,
    )


_RequirementOutput = Annotated[
    _SkillRequirementOutput | _OtherRequirementOutput,
    Field(discriminator="type"),
]


PROVIDER_RAW_REQUIREMENTS_LIMIT = 64


class _RequirementsOutput(_StrictModel):
    requirements: list[_RequirementOutput] = Field(
        min_length=1,
        max_length=PROVIDER_RAW_REQUIREMENTS_LIMIT,
    )


class DisabledJobRequirementExtractor(AbstractJobRequirementExtractor):
    @property
    def model_name(self) -> str:
        return "disabled"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        raise RequirementExtractorUnavailableError(
            "Requirement extractor is disabled. Configure REQUIREMENT_EXTRACTOR_PROVIDER."
        )


class FixtureJobRequirementExtractor(AbstractJobRequirementExtractor):
    """Deterministic CI/demo adapter; not a substitute for live model quality."""

    @property
    def model_name(self) -> str:
        return "fixture-requirement-extractor"

    def extract(self, description: str) -> JobRequirementExtractorResult:
        segments = _segments(description)
        requirements: list[ProposedJobRequirement] = []
        for segment in segments:
            importance = _importance(segment)
            requirement_type = _requirement_type(segment)
            capabilities = _capabilities(segment)
            if requirement_type is RequirementType.SKILL and capabilities:
                requirements.extend(
                    ProposedJobRequirement(
                        type=requirement_type,
                        original_text=segment,
                        normalized_capability=capability,
                        importance=importance,
                        evidence_span=segment,
                        confidence=0.95,
                    )
                    for capability in capabilities
                )
                continue
            requirements.append(
                ProposedJobRequirement(
                    type=requirement_type,
                    original_text=segment,
                    normalized_capability=_fallback_capability(requirement_type, segment),
                    importance=importance,
                    evidence_span=segment,
                    confidence=0.9,
                )
            )
        if not requirements:
            raise RequirementExtractorFailedError(
                "Fixture Requirement extractor found no requirement-like text"
            )
        return JobRequirementExtractorResult(
            output=JobRequirementExtractionOutput(requirements=tuple(requirements[:50])),
            model=self.model_name,
        )


class FallbackJobRequirementExtractor(AbstractJobRequirementExtractor):
    """Route transient primary unavailability to one explicitly configured fallback."""

    def __init__(
        self,
        *,
        primary: AbstractJobRequirementExtractor,
        fallback: AbstractJobRequirementExtractor,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def model_name(self) -> str:
        return self._primary.model_name

    @property
    def max_provider_calls_per_execution(self) -> int:
        return (
            self._primary.max_provider_calls_per_execution
            + self._fallback.max_provider_calls_per_execution
        )

    def extract(self, description: str) -> JobRequirementExtractorResult:
        try:
            return self._primary.extract(description)
        except RequirementExtractorUnavailableError as primary_error:
            primary_calls = primary_error.provider_calls
            try:
                fallback_result = self._fallback.extract(description)
            except RequirementExtractorUnavailableError as fallback_error:
                fallback_error.provider_calls += primary_calls
                raise
            except RequirementExtractorFailedError as fallback_error:
                fallback_error.provider_calls += primary_calls
                raise
            return JobRequirementExtractorResult(
                output=fallback_result.output,
                model=fallback_result.model,
                input_tokens=fallback_result.input_tokens,
                output_tokens=fallback_result.output_tokens,
                provider_calls=primary_calls + fallback_result.provider_calls,
            )


class OpenAIJobRequirementExtractor(AbstractJobRequirementExtractor):
    """OpenAI-compatible adapter using strict JSON Schema output."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        api_style: str = "responses",
        enable_thinking: bool | None = None,
        max_completion_tokens: int | None = None,
        timeout_seconds: float = 60.0,
        client: httpx.Client | None = None,
        retry_max_attempts: int = 1,
        retry_backoff_seconds: float = 0.25,
        sleep_fn: Callable[[float], None] = time.sleep,
        circuit_failure_threshold: int = 0,
        circuit_cooldown_seconds: float = 30.0,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_key = api_key
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._api_style = api_style.strip().casefold()
        self._enable_thinking = enable_thinking
        self._max_completion_tokens = max_completion_tokens
        if retry_max_attempts < 1:
            raise ValueError("retry_max_attempts must be at least 1")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")
        if circuit_failure_threshold < 0:
            raise ValueError("circuit_failure_threshold must be non-negative")
        if circuit_cooldown_seconds < 0:
            raise ValueError("circuit_cooldown_seconds must be non-negative")
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._retry_max_attempts = retry_max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._sleep_fn = sleep_fn
        self._circuit_failure_threshold = circuit_failure_threshold
        self._circuit_cooldown_seconds = circuit_cooldown_seconds
        self._monotonic_fn = monotonic_fn
        self._circuit_failure_count = 0
        self._circuit_open_until: float | None = None

    @property
    def model_name(self) -> str:
        return self._model or "openai-unconfigured"

    @property
    def max_provider_calls_per_execution(self) -> int:
        return self._retry_max_attempts

    def extract(self, description: str) -> JobRequirementExtractorResult:
        if not self._api_key or not self._model:
            raise RequirementExtractorUnavailableError(
                "OpenAI Requirement extractor requires OPENAI_API_KEY and REQUIREMENT_EXTRACTOR_MODEL."
            )
        source_candidates = _source_candidates(description)
        source_candidate_text = _render_extraction_input(description, source_candidates)
        schema = _RequirementsOutput.model_json_schema(by_alias=True)
        if self._api_style == "responses":
            request_url = f"{self._base_url}/responses"
            request_body = {
                "model": self._model,
                "store": False,
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": _SYSTEM_PROMPT}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": source_candidate_text}],
                    },
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "job_requirement_extraction",
                        "description": (
                            "Evidence-grounded requirements extracted from one Job description"
                        ),
                        "strict": True,
                        "schema": schema,
                    }
                },
            }
            output_text = _response_output_text
            input_tokens_key = "input_tokens"
            output_tokens_key = "output_tokens"
        elif self._api_style == "chat_completions":
            request_url = f"{self._base_url}/chat/completions"
            request_body = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": source_candidate_text},
                ],
                "stream": False,
                "temperature": 0,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "job_requirement_extraction",
                        "description": (
                            "Evidence-grounded requirements extracted from one Job description"
                        ),
                        "strict": True,
                        "schema": schema,
                    },
                },
            }
            if self._enable_thinking is not None:
                request_body["enable_thinking"] = self._enable_thinking
            if self._max_completion_tokens is not None:
                request_body["max_completion_tokens"] = self._max_completion_tokens
            output_text = _chat_completion_output_text
            input_tokens_key = "prompt_tokens"
            output_tokens_key = "completion_tokens"
        else:
            raise RequirementExtractorUnavailableError(
                "OpenAI Requirement extractor API style must be responses or "
                "chat_completions."
            )

        payload: Any = None
        provider_text: str | None = None
        failure_input_tokens: int | None = None
        failure_output_tokens: int | None = None
        provider_finish_reason: str | None = None
        provider_call_counter = [0]

        try:
            response = self._post_with_retry(
                request_url,
                request_body,
                provider_call_counter=provider_call_counter,
            )
            payload = response.json()
            usage = payload.get("usage") if isinstance(payload, dict) else None
            failure_input_tokens = _optional_int(usage, input_tokens_key)
            failure_output_tokens = _optional_int(usage, output_tokens_key)
            provider_finish_reason = _provider_finish_reason(payload, api_style=self._api_style)
            provider_text = output_text(payload)
            parsed = _RequirementsOutput.model_validate_json(provider_text)
            _validate_source_candidate_ids(parsed, source_candidates)
            _validate_unique_source_facts(
                parsed,
                provider_calls=provider_call_counter[0],
            )
        except RequirementExtractorFailedError:
            raise
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            trace_id = _response_trace_id(error.response)
            trace_suffix = f", traceId={trace_id}" if trace_id else ""
            message = (
                "OpenAI Requirement extractor failed: "
                f"HTTPStatusError(status={status_code}{trace_suffix})"
            )
            if status_code in {429, 503, 504}:
                raise RequirementExtractorUnavailableError(
                    message,
                    status_code=status_code,
                    provider_calls=provider_call_counter[0],
                ) from error
            raise RequirementExtractorFailedError(
                message,
                provider_calls=provider_call_counter[0],
            ) from error
        except ValidationError as error:
            message, failure_stage = _structured_output_validation_error_message(
                error,
                provider_finish_reason=provider_finish_reason,
                input_tokens=failure_input_tokens,
                output_tokens=failure_output_tokens,
                output_chars=len(provider_text) if provider_text is not None else None,
                requested_max_completion_tokens=self._max_completion_tokens,
            )
            raise RequirementExtractorFailedError(
                message,
                failure_stage=failure_stage,
                input_tokens=failure_input_tokens,
                output_tokens=failure_output_tokens,
                provider_finish_reason=provider_finish_reason,
                output_chars=len(provider_text) if provider_text is not None else None,
                requested_max_completion_tokens=self._max_completion_tokens,
                provider_calls=provider_call_counter[0],
            ) from error
        except json.JSONDecodeError as error:
            raise RequirementExtractorFailedError(
                "OpenAI Requirement extractor failed: "
                "ProviderOutputError(failureStage=provider_response_json, "
                "reason=invalid_json)",
                provider_calls=provider_call_counter[0],
            ) from error
        except KeyError as error:
            raise RequirementExtractorFailedError(
                "OpenAI Requirement extractor failed: "
                "ProviderOutputError(failureStage=provider_response_shape, "
                f"reason=missing_key, key={str(error)[:128]})",
                provider_calls=provider_call_counter[0],
            ) from error
        except httpx.TimeoutException as error:
            raise RequirementExtractorUnavailableError(
                "OpenAI Requirement extractor failed: "
                f"ProviderTransportError(failureStage=transport, errorType={type(error).__name__})",
                provider_calls=provider_call_counter[0],
            ) from error
        except httpx.HTTPError as error:
            raise RequirementExtractorFailedError(
                "OpenAI Requirement extractor failed: "
                f"ProviderTransportError(failureStage=transport, errorType={type(error).__name__})",
                provider_calls=provider_call_counter[0],
            ) from error

        usage = payload.get("usage") if isinstance(payload, dict) else None
        return JobRequirementExtractorResult(
            output=JobRequirementExtractionOutput(
                requirements=tuple(
                    ProposedJobRequirement(
                        type=item.type,
                        original_text=item.original_text,
                        normalized_capability=(
                            item.normalized_capability
                            if item.type is RequirementType.SKILL
                            else (
                                item.normalized_capability.strip() or None
                                if item.normalized_capability is not None
                                else None
                            )
                        ),
                        importance=item.importance,
                        evidence_span=source_candidates[item.source_candidate_id],
                        confidence=item.confidence,
                    )
                    for item in parsed.requirements
                )
            ),
            model=self._model,
            input_tokens=_optional_int(usage, input_tokens_key),
            output_tokens=_optional_int(usage, output_tokens_key),
            provider_calls=provider_call_counter[0],
        )

    def _post_with_retry(
        self,
        request_url: str,
        request_body: dict[str, Any],
        *,
        provider_call_counter: list[int],
    ) -> httpx.Response:
        self._ensure_circuit_allows_request()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        for attempt in range(1, self._retry_max_attempts + 1):
            try:
                provider_call_counter[0] += 1
                if self._client is not None:
                    response = self._client.post(
                        request_url,
                        headers=headers,
                        json=request_body,
                    )
                else:
                    with httpx.Client(timeout=self._timeout_seconds) as client:
                        response = client.post(
                            request_url,
                            headers=headers,
                            json=request_body,
                        )
                response.raise_for_status()
                self._reset_circuit()
                return response
            except httpx.HTTPStatusError as error:
                if error.response.status_code not in {429, 503, 504}:
                    raise
                if attempt >= self._retry_max_attempts:
                    self._record_circuit_failure()
                    raise
            except httpx.TimeoutException:
                if attempt >= self._retry_max_attempts:
                    self._record_circuit_failure()
                    raise
            self._sleep_fn(self._retry_backoff_seconds * (2 ** (attempt - 1)))
        raise AssertionError("retry loop exhausted without returning or raising")

    def _ensure_circuit_allows_request(self) -> None:
        if self._circuit_failure_threshold <= 0 or self._circuit_open_until is None:
            return
        if self._monotonic_fn() >= self._circuit_open_until:
            self._circuit_open_until = None
            return
        raise RequirementExtractorUnavailableError(
            "OpenAI Requirement extractor circuit is open after repeated transient provider failures."
        )

    def _record_circuit_failure(self) -> None:
        if self._circuit_failure_threshold <= 0:
            return
        self._circuit_failure_count += 1
        if self._circuit_failure_count >= self._circuit_failure_threshold:
            self._circuit_open_until = self._monotonic_fn() + self._circuit_cooldown_seconds

    def _reset_circuit(self) -> None:
        self._circuit_failure_count = 0
        self._circuit_open_until = None


def _source_candidates(description: str) -> dict[str, str]:
    candidates: dict[str, str] = {}
    for line in description.splitlines():
        raw = line.strip()
        if not raw:
            continue
        candidate_id = f"S{len(candidates) + 1:04d}"
        candidates[candidate_id] = raw
    if not candidates:
        raise RequirementExtractorFailedError(
            "Requirement extractor input contains no non-empty source candidates"
        )
    return candidates


def _render_extraction_input(description: str, candidates: dict[str, str]) -> str:
    candidate_text = "\n".join(
        f"[{candidate_id}] {text}" for candidate_id, text in candidates.items()
    )
    return (
        "JOB DESCRIPTION (use this full raw text to understand section, scope, and "
        "cross-line semantics):\n"
        f"{description}\n\n"
        "SOURCE CANDIDATES (use only these IDs to anchor persisted evidence):\n"
        f"{candidate_text}"
    )


def _validate_source_candidate_ids(
    output: _RequirementsOutput,
    candidates: dict[str, str],
) -> None:
    invalid = sorted(
        {
            item.source_candidate_id
            for item in output.requirements
            if item.source_candidate_id not in candidates
        }
    )
    if invalid:
        raise RequirementExtractorFailedError(
            "OpenAI Requirement extractor returned unknown sourceCandidateId: "
            + ", ".join(invalid)
        )


def _validate_unique_source_facts(
    output: _RequirementsOutput,
    *,
    provider_calls: int,
) -> None:
    """Fail closed when one Provider source fact is copied into multiple rows.

    v42.96 human review showed the same source candidate + original text being emitted
    repeatedly with only type/capability changed. That creates duplicate matching weight
    downstream. A Provider may still emit multiple Requirements from one source candidate,
    but each row must own a distinct verbatim ``originalText`` slice.
    """
    seen: dict[tuple[str, str], int] = {}
    for index, item in enumerate(output.requirements):
        original_identity = re.sub(r"\s+", "", item.original_text).casefold()
        identity = (item.source_candidate_id, original_identity)
        previous = seen.get(identity)
        if previous is not None:
            raise RequirementExtractorFailedError(
                "OpenAI Requirement extractor violated source-fact uniqueness: "
                f"Requirement {index} reuses sourceCandidateId={item.source_candidate_id} "
                f"and the same originalText as Requirement {previous}",
                failure_stage="provider_contract_source_fact_uniqueness",
                provider_calls=provider_calls,
            )
        seen[identity] = index


_CAPABILITY_ALIASES = (
    ("React", ("react.js", "reactjs", "react")),
    ("TypeScript", ("typescript",)),
    ("JavaScript", ("javascript",)),
    ("Next.js", ("next.js", "nextjs")),
    ("Electron", ("electron",)),
    ("Python", ("python",)),
    ("FastAPI", ("fastapi",)),
    ("SQLAlchemy", ("sqlalchemy",)),
    ("Java", ("java",)),
    ("Spring Boot", ("spring boot", "springboot")),
    ("Docker", ("docker",)),
    ("Kubernetes", ("kubernetes", "k8s")),
    ("PostgreSQL", ("postgresql", "postgres")),
    ("RAG", ("rag", "检索增强生成")),
    ("Agent", ("agent", "智能体")),
    ("LLM", ("llm", "大语言模型")),
)


def _segments(description: str) -> list[str]:
    result: list[str] = []
    for line in description.splitlines():
        stripped = re.sub(r"^[\s\-•*\d.、）)]+", "", line).strip()
        for segment in re.split(r"(?<=[。；;])\s*", stripped):
            segment = segment.strip()
            if segment.endswith((":", "：")) and not _capabilities(segment):
                continue
            if len(segment) >= 4 and _looks_like_requirement(segment):
                result.append(segment)
    return result[:30]


def _looks_like_requirement(text: str) -> bool:
    markers = (
        "要求",
        "必须",
        "熟练",
        "精通",
        "掌握",
        "熟悉",
        "了解",
        "经验",
        "学历",
        "本科",
        "硕士",
        "负责",
        "参与",
        "优先",
        "加分",
        "能够",
        "接受",
        "出差",
    )
    folded = text.casefold()
    return any(marker in text for marker in markers) or any(
        alias in folded
        for _name, aliases in _CAPABILITY_ALIASES
        for alias in aliases
    )


def _importance(text: str) -> RequirementImportance:
    if any(marker in text for marker in ("加分", "优先", "更佳", "bonus")):
        return RequirementImportance.BONUS
    if any(
        marker in text
        for marker in ("必须", "要求", "至少", "以上", "精通", "熟练掌握", "本科")
    ):
        return RequirementImportance.MUST_HAVE
    return RequirementImportance.PREFERRED


def _requirement_type(text: str) -> RequirementType:
    if any(marker in text for marker in ("学历", "本科", "硕士", "博士", "大专")):
        return RequirementType.EDUCATION
    if re.search(r"\d+(?:\.\d+)?\s*年", text) or "经验" in text:
        if _capabilities(text):
            return RequirementType.SKILL
        return RequirementType.EXPERIENCE
    if any(marker in text for marker in ("负责", "参与", "承担", "推进", "设计并")):
        return RequirementType.RESPONSIBILITY
    if any(marker in text for marker in ("金融", "支付", "电商", "医疗", "游戏", "制造")):
        return RequirementType.DOMAIN
    if any(marker in text for marker in ("出差", "驻场", "英语", "全职", "年龄")):
        return RequirementType.CONSTRAINT
    return RequirementType.SKILL


def _capabilities(text: str) -> list[str]:
    folded = text.casefold()
    return [
        name
        for name, aliases in _CAPABILITY_ALIASES
        if any(alias in folded for alias in aliases)
    ]


def _fallback_capability(
    requirement_type: RequirementType,
    text: str,
) -> str | None:
    if requirement_type is RequirementType.EXPERIENCE:
        return "Professional Experience"
    if requirement_type is RequirementType.EDUCATION:
        return "Education"
    if requirement_type is RequirementType.DOMAIN:
        for name in ("FinTech", "Payments", "E-commerce", "Healthcare", "Gaming", "Manufacturing"):
            marker = {
                "FinTech": "金融",
                "Payments": "支付",
                "E-commerce": "电商",
                "Healthcare": "医疗",
                "Gaming": "游戏",
                "Manufacturing": "制造",
            }[name]
            if marker in text:
                return name
    if requirement_type is RequirementType.CONSTRAINT:
        return "Employment Constraint"
    return None


def _response_output_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise _provider_output_error("provider_response_shape", "response_not_object")
    for item in _iter_dicts(payload.get("output")):
        if item.get("type") != "message":
            continue
        for content in _iter_dicts(item.get("content")):
            if content.get("type") == "refusal":
                raise _provider_output_error("provider_refusal", "refused")
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise _provider_output_error("provider_response_shape", "missing_output_text")


def _chat_completion_output_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise _provider_output_error("provider_response_shape", "response_not_object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise _provider_output_error("provider_response_shape", "missing_choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise _provider_output_error("provider_response_shape", "choice_not_object")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise _provider_output_error("provider_response_shape", "missing_message")
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal:
        raise _provider_output_error("provider_refusal", "refused")
    content = message.get("content")
    if isinstance(content, str) and content:
        return content
    for item in _iter_dicts(content):
        if item.get("type") == "refusal":
            raise _provider_output_error("provider_refusal", "refused")
        if item.get("type") in {"text", "output_text"} and isinstance(
            item.get("text"), str
        ):
            return item["text"]
    raise _provider_output_error("provider_response_shape", "missing_text_content")


def _provider_output_error(failure_stage: str, reason: str) -> RequirementExtractorFailedError:
    return RequirementExtractorFailedError(
        "OpenAI Requirement extractor failed: "
        f"ProviderOutputError(failureStage={failure_stage}, reason={reason})",
        failure_stage=failure_stage,
    )


def _structured_output_validation_error_message(
    error: ValidationError,
    *,
    provider_finish_reason: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    output_chars: int | None = None,
    requested_max_completion_tokens: int | None = None,
) -> tuple[str, str]:
    issues = error.errors(include_url=False, include_context=False, include_input=False)
    failure_stage = (
        "structured_output_json"
        if any(issue.get("type") == "json_invalid" for issue in issues)
        else "structured_output_validation"
    )
    summaries: list[str] = []
    for issue in issues[:5]:
        location = ".".join(str(part) for part in issue.get("loc", ())) or "root"
        issue_type = str(issue.get("type") or "unknown")
        summaries.append(f"{location}:{issue_type}")
    issue_summary = ",".join(summaries) or "unknown"
    diagnostic_parts = [
        f"finishReason={_safe_diagnostic_value(provider_finish_reason) if provider_finish_reason else 'unknown'}",
        f"inputTokens={input_tokens if input_tokens is not None else 'unknown'}",
        f"outputTokens={output_tokens if output_tokens is not None else 'unknown'}",
        f"outputChars={output_chars if output_chars is not None else 'unknown'}",
        (
            "requestedMaxCompletionTokens="
            f"{requested_max_completion_tokens if requested_max_completion_tokens is not None else 'provider_default'}"
        ),
    ]
    return (
        (
            "OpenAI Requirement extractor failed: "
            f"ValidationError(failureStage={failure_stage}, issueCount={len(issues)}, "
            f"issues={issue_summary}, {', '.join(diagnostic_parts)})"
        ),
        failure_stage,
    )


def _provider_finish_reason(payload: Any, *, api_style: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    if api_style == "chat_completions":
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return None
        value = choices[0].get("finish_reason")
        return value.strip()[:64] if isinstance(value, str) and value.strip() else None
    incomplete_details = payload.get("incomplete_details")
    if isinstance(incomplete_details, dict):
        reason = incomplete_details.get("reason")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()[:64]
    status = payload.get("status")
    return status.strip()[:64] if isinstance(status, str) and status.strip() else None


def _safe_diagnostic_value(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value)[:64] or "unknown"


def _iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(value, list):
        return ()
    return (item for item in value if isinstance(item, dict))


def _optional_int(value: Any, key: str) -> int | None:
    if not isinstance(value, dict):
        return None
    result = value.get(key)
    return result if isinstance(result, int) and result >= 0 else None


def _response_trace_id(response: httpx.Response) -> str | None:
    for header in ("x-trace-id", "trace-id"):
        value = response.headers.get(header)
        if value and value.strip():
            return value.strip()[:128]
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("traceId")
    return value.strip()[:128] if isinstance(value, str) and value.strip() else None


_SYSTEM_PROMPT = """Extract structured JobRequirements from one Job description.

Rules:
- Extract only requirements explicitly present in the Job description.
- Never infer requirements from the job title, company, industry stereotypes, or general knowledge.
- The user input contains two parts: the full raw Job description for understanding section/scope/cross-line semantics, followed by source candidates in the form `[S0001] exact JD text` for evidence anchoring. Use the full Job description to interpret requirement meaning and scope; use sourceCandidateId only to select persisted evidence. For every requirement, sourceCandidateId must be one of those candidate IDs. The backend, not the model, will persist evidenceSpan from that candidate's raw JD text.
- originalText must be copied verbatim as one contiguous substring from the selected source candidate. Do not delete, insert, reorder, paraphrase, or normalize words. If an exact originalText cannot be copied from one candidate, omit that requirement rather than inventing text or combining candidates.
- Classify type as skill, experience, education, responsibility, domain, or constraint.
- Extract both explicit job responsibilities/duties/work content and qualifications/requirements. Responsibilities are first-class JobRequirements used by downstream matching and preparation; do not return only qualifications when explicit duties are present.
- When the Job description presents distinct responsibility/action lines, preserve each materially distinct explicit duty as a separate `responsibility` Requirement when it can be anchored to one source candidate. Do not omit a duty merely because it is not an eligibility qualification, and do not relabel a duty as `skill` only because it mentions a technical capability.
- Classify importance by the requirement's actual scope. In an explicit requirements/qualifications section, default to must_have unless that exact requirement is softened by optional/preferred/bonus wording.
- A softening modifier such as 优先/加分/preferred/optional applies only to the clause it modifies; do not downgrade adjacent hard constraints in the same sentence. If one sentence mixes hard and soft clauses, split them into separate requirements when the input provides separable verbatim spans.
- A waiver or exception such as 可放宽/可豁免/waived/exception weakens only the threshold or condition it modifies. Do not emit the strict threshold as an independent must_have and do not emit the waiver itself as a separate preferred requirement. When the waiver-bearing wording is contiguous, preserve that affected condition as one non-blocking preferred requirement unless another clause remains explicitly unconditional. For example, a years-of-experience threshold followed by an exceptional-candidate waiver is not an unconditional hard gate.
- Do not emit more than one Requirement with the same sourceCandidateId and the same exact originalText. One contiguous source fact must not be copied into multiple rows only to attach different types or normalized capabilities.
- If one contiguous clause mentions multiple capabilities but those capabilities cannot each be copied as distinct verbatim originalText substrings, emit one compound constraint instead of duplicating the full clause for each capability.
- For alternative or cardinality groups such as "at least N of the following", "one of", "any one", or "任意一种", preserve the mandatory group constraint and must not make every child independently must_have. Emit child capabilities only when each child can be anchored to its own distinct verbatim originalText/source candidate; never duplicate the same full originalText for the parent and its children.
- Concrete examples such as 如/例如/such as/e.g. illustrate an umbrella requirement rather than adding separate hard constraints. Example children must not become independent must_have requirements unless the Job description explicitly requires those children outside the example wording; prefer the umbrella requirement with its verbatim span and omit redundant example-child requirements.
- Use bonus only for explicitly optional, plus, preferred, or bonus requirements. Use preferred only for explicitly desirable-but-not-mandatory requirements or alternative child capabilities governed by a separate mandatory group constraint.
- Normalize capability aliases when supported by the text, for example React.js/ReactJS → React.
- Skill requirements must include normalizedCapability.
- Omit unsupported requirements instead of guessing.
- Return no prose outside the strict schema.
"""
