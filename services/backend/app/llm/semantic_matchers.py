"""Semantic Match provider adapters used by the Phase 4 workflow."""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.application.evidence_retrieval.models import EvidenceRelevanceTier
from app.application.ports.semantic_matcher import AbstractSemanticMatcher
from app.application.semantic_match.errors import (
    SemanticMatcherFailedError,
    SemanticMatcherUnavailableError,
)
from app.application.semantic_match.models import (
    SemanticMatchAssessmentOutput,
    SemanticMatchOutput,
    SemanticMatcherResult,
    SemanticMatchVerdict,
    SemanticRequirementInput,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _SemanticAssessmentSchema(_StrictModel):
    requirement_id: str = Field(alias="requirementId", min_length=1, max_length=255)
    verdict: SemanticMatchVerdict
    evidence_ids: list[str] = Field(alias="evidenceIds", max_length=50)
    reason: str = Field(min_length=1, max_length=2000)


class _SemanticOutputSchema(_StrictModel):
    assessments: list[_SemanticAssessmentSchema] = Field(min_length=1, max_length=50)


class DisabledSemanticMatcher(AbstractSemanticMatcher):
    @property
    def model_name(self) -> str:
        return "semantic-match-disabled"

    def match(
        self,
        requirements: tuple[SemanticRequirementInput, ...],
    ) -> SemanticMatcherResult:
        raise SemanticMatcherUnavailableError(
            "Semantic Match provider is disabled. Configure an approved provider before execution."
        )


class FixtureSemanticMatcher(AbstractSemanticMatcher):
    """Deterministic local matcher for tests and contract validation only."""

    @property
    def model_name(self) -> str:
        return "fixture-semantic-matcher"

    def match(
        self,
        requirements: tuple[SemanticRequirementInput, ...],
    ) -> SemanticMatcherResult:
        assessments: list[SemanticMatchAssessmentOutput] = []
        for requirement in requirements:
            direct_ids = tuple(
                item.evidence_id
                for item in requirement.candidates
                if item.relevance_tier is EvidenceRelevanceTier.DIRECT
            )
            if direct_ids:
                assessments.append(
                    SemanticMatchAssessmentOutput(
                        requirement_id=requirement.requirement_id,
                        verdict=SemanticMatchVerdict.MATCHED,
                        evidence_ids=direct_ids,
                        reason="Fixture: direct evidence explicitly supports the requirement.",
                    )
                )
                continue

            related_ids = tuple(item.evidence_id for item in requirement.candidates)
            assessments.append(
                SemanticMatchAssessmentOutput(
                    requirement_id=requirement.requirement_id,
                    verdict=SemanticMatchVerdict.PARTIAL,
                    evidence_ids=related_ids,
                    reason=(
                        "Fixture: retrieved evidence is relevant but does not explicitly prove "
                        "the full requirement."
                    ),
                )
            )

        return SemanticMatcherResult(
            output=SemanticMatchOutput(assessments=tuple(assessments)),
            model=self.model_name,
        )


class OpenAISemanticMatcher(AbstractSemanticMatcher):
    """OpenAI-compatible Semantic Match adapter with strict structured output."""

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
    ) -> None:
        self._api_key = api_key
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._api_style = api_style.strip().casefold()
        self._enable_thinking = enable_thinking
        self._max_completion_tokens = max_completion_tokens
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def model_name(self) -> str:
        return self._model or "openai-unconfigured"

    def match(
        self,
        requirements: tuple[SemanticRequirementInput, ...],
    ) -> SemanticMatcherResult:
        if not self._api_key or not self._model:
            raise SemanticMatcherUnavailableError(
                "OpenAI Semantic Match requires OPENAI_API_KEY and SEMANTIC_MATCH_MODEL."
            )
        if not requirements:
            raise SemanticMatcherFailedError(
                "OpenAI Semantic Match requires at least one requirement input."
            )

        schema = _SemanticOutputSchema.model_json_schema(by_alias=True)
        user_payload = json.dumps(
            _semantic_input_payload(requirements),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if self._api_style == "responses":
            request_url = f"{self._base_url}/responses"
            request_body: dict[str, Any] = {
                "model": self._model,
                "store": False,
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": _SYSTEM_PROMPT}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_payload}],
                    },
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "semantic_match",
                        "description": (
                            "Evidence-grounded semantic judgments for retrieved Profile Evidence"
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
                    {"role": "user", "content": user_payload},
                ],
                "stream": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "semantic_match",
                        "description": (
                            "Evidence-grounded semantic judgments for retrieved Profile Evidence"
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
            raise SemanticMatcherUnavailableError(
                "OpenAI Semantic Match API style must be responses or chat_completions."
            )

        try:
            if self._client is not None:
                response = self._client.post(
                    request_url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                )
            else:
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(
                        request_url,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json=request_body,
                    )
            response.raise_for_status()
            payload = response.json()
            parsed = _SemanticOutputSchema.model_validate_json(output_text(payload))
        except SemanticMatcherFailedError:
            raise
        except httpx.HTTPStatusError as error:
            trace_id = _response_trace_id(error.response)
            trace_suffix = f", traceId={trace_id}" if trace_id else ""
            raise SemanticMatcherFailedError(
                "OpenAI Semantic Match failed: "
                f"HTTPStatusError(status={error.response.status_code}{trace_suffix})"
            ) from error
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError) as error:
            raise SemanticMatcherFailedError(
                f"OpenAI Semantic Match failed: {type(error).__name__}"
            ) from error

        usage = payload.get("usage") if isinstance(payload, dict) else None
        return SemanticMatcherResult(
            output=SemanticMatchOutput(
                assessments=tuple(
                    SemanticMatchAssessmentOutput(
                        requirement_id=item.requirement_id,
                        verdict=item.verdict,
                        evidence_ids=tuple(item.evidence_ids),
                        reason=item.reason,
                    )
                    for item in parsed.assessments
                )
            ),
            model=self._model,
            input_tokens=_optional_int(usage, input_tokens_key),
            output_tokens=_optional_int(usage, output_tokens_key),
        )


def _semantic_input_payload(
    requirements: tuple[SemanticRequirementInput, ...],
) -> dict[str, object]:
    return {
        "requirements": [
            {
                "requirementId": item.requirement_id,
                "type": item.type.value,
                "importance": item.importance.value,
                "originalText": item.original_text,
                "normalizedCapability": item.normalized_capability,
                "candidates": [
                    {
                        "evidenceId": candidate.evidence_id,
                        "evidenceType": candidate.evidence_type.value,
                        "summary": candidate.summary,
                        "relevanceTier": candidate.relevance_tier.value,
                        "retrievalBasis": candidate.retrieval_basis.value,
                    }
                    for candidate in item.candidates
                ],
            }
            for item in requirements
        ]
    }


def _response_output_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise SemanticMatcherFailedError("OpenAI response must be a JSON object")
    for item in _iter_dicts(payload.get("output")):
        if item.get("type") != "message":
            continue
        for content in _iter_dicts(item.get("content")):
            if content.get("type") == "refusal":
                raise SemanticMatcherFailedError("OpenAI refused Semantic Match")
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise SemanticMatcherFailedError("OpenAI response contained no output_text")


def _chat_completion_output_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise SemanticMatcherFailedError(
            "OpenAI Chat Completions response must be a JSON object"
        )
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise SemanticMatcherFailedError(
            "OpenAI Chat Completions response contained no choices"
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise SemanticMatcherFailedError(
            "OpenAI Chat Completions choice must be a JSON object"
        )
    message = choice.get("message")
    if not isinstance(message, dict):
        raise SemanticMatcherFailedError(
            "OpenAI Chat Completions response contained no message"
        )
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal:
        raise SemanticMatcherFailedError("OpenAI refused Semantic Match")
    content = message.get("content")
    if isinstance(content, str) and content:
        return content
    for item in _iter_dicts(content):
        if item.get("type") == "refusal":
            raise SemanticMatcherFailedError("OpenAI refused Semantic Match")
        if item.get("type") in {"text", "output_text"} and isinstance(
            item.get("text"), str
        ):
            return item["text"]
    raise SemanticMatcherFailedError(
        "OpenAI Chat Completions response contained no text content"
    )


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


_SYSTEM_PROMPT = """Judge how well each supplied Profile Evidence candidate supports one JobRequirement.

Rules:
- Use only the supplied JobRequirement and candidate Evidence. Do not use outside knowledge or infer unstated career facts.
- Return each requested requirement exactly once and in the same order.
- matched means cited Evidence explicitly demonstrates the requirement.
- related-only Evidence can never justify matched.
- Use partial when the supplied Evidence demonstrates a meaningful related or transferable capability but does not explicitly prove the full requirement.
- Do not choose not_matched only because the exact target technology or phrase is absent. If the Evidence concretely demonstrates a transferable sub-capability or closely related implementation work, use partial.
- A candidate marked relevanceTier=related is only a retrieval signal that it is worth judging; it is not proof by itself. If the candidate content is merely adjacent and does not demonstrate a meaningful transferable capability, use not_matched.
- partial must cite the real candidate evidenceIds that make it relevant.
- not_matched must return an empty evidenceIds list.
- Never invent evidenceIds, skills, years of experience, education, employers, responsibilities, or achievements.
- Do not output or change overall Eligibility, recommendation, ranking, probability, or score. Deterministic Eligibility is owned by another gate.

Calibration examples:
1. Requirement: 熟悉 MCP 协议
   Evidence: 实现 Agent Function Calling、工具调用和工具集成
   Candidate tier: related
   Verdict: partial
   Why: the Evidence demonstrates closely related tool-integration capability, but does not explicitly prove MCP experience.

2. Requirement: 熟悉 FastAPI
   Evidence: 使用 Python 开发 REST API 服务，但没有明确使用 FastAPI
   Candidate tier: related
   Verdict: partial
   Why: the Evidence demonstrates transferable Python API implementation capability, but does not explicitly prove FastAPI usage.

3. Requirement: 熟悉 MCP 协议
   Evidence: 使用 React 开发 AI 聊天界面
   Candidate tier: related
   Verdict: not_matched
   Why: AI product adjacency alone does not demonstrate protocol or tool-integration capability.

4. Requirement: 精通 Java
   Evidence: 使用 Java 开发订单服务并负责线上问题排查
   Candidate tier: direct
   Verdict: matched
   Why: the Evidence explicitly demonstrates Java implementation experience.

Return no prose outside the strict schema.
"""
