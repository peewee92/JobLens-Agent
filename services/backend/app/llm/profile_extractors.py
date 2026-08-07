"""Profile Extractor adapters for disabled, fixture and OpenAI providers."""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.application.ports.profile_extractor import AbstractProfileExtractor
from app.application.profile_extraction import (
    ProfileExtractionOutput,
    ProfileExtractorFailedError,
    ProfileExtractorResult,
    ProfileExtractorUnavailableError,
    ProposedEvidence,
    ProposedSkill,
)
from app.domain.career_context import EvidenceType, SkillLevel


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _EvidenceOutput(_StrictModel):
    key: str = Field(min_length=1, max_length=120)
    type: EvidenceType
    summary: str = Field(min_length=1, max_length=1000)
    source: str = Field(min_length=1, max_length=255)
    evidence_span: str = Field(alias="evidenceSpan", min_length=1, max_length=4000)


class _SkillOutput(_StrictModel):
    name: str = Field(min_length=1, max_length=255)
    level: SkillLevel
    evidence_keys: list[str] = Field(alias="evidenceKeys", min_length=1)


class _ProfileOutput(_StrictModel):
    headline: str = Field(min_length=1, max_length=500)
    years_of_experience: float | None = Field(alias="yearsOfExperience")
    evidence: list[_EvidenceOutput] = Field(min_length=1)
    skills: list[_SkillOutput] = Field(min_length=1)
    warnings: list[str]


class DisabledProfileExtractor(AbstractProfileExtractor):
    @property
    def model_name(self) -> str:
        return "disabled"

    def extract(self, resume_text: str) -> ProfileExtractorResult:
        raise ProfileExtractorUnavailableError(
            "Profile extractor is disabled. Configure PROFILE_EXTRACTOR_PROVIDER."
        )


class FixtureProfileExtractor(AbstractProfileExtractor):
    """Deterministic test/demo adapter; it is not a quality substitute for an LLM."""

    _SKILLS = (
        "React",
        "TypeScript",
        "Electron",
        "Agent",
        "RAG",
        "Python",
        "FastAPI",
        "SQLAlchemy",
        "Next.js",
    )

    @property
    def model_name(self) -> str:
        return "fixture-profile-extractor"

    def extract(self, resume_text: str) -> ProfileExtractorResult:
        lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
        if not lines:
            raise ProfileExtractorFailedError("Fixture extractor received empty text")

        selected = [
            line
            for line in lines
            if len(line) >= 8
            and any(
                marker.casefold() in line.casefold()
                for marker in (*self._SKILLS, "项目", "负责", "开发", "实现", "工作")
            )
        ][:4]
        if not selected:
            selected = [max(lines, key=len)]

        evidence = tuple(
            ProposedEvidence(
                key=f"resume-evidence-{index}",
                type=_fixture_evidence_type(line),
                summary=line,
                source="resume",
                evidence_span=line,
            )
            for index, line in enumerate(selected, start=1)
        )
        skills = []
        for skill in self._SKILLS:
            supporting = tuple(
                item.key
                for item in evidence
                if skill.casefold() in item.evidence_span.casefold()
            )
            if supporting:
                skills.append(
                    ProposedSkill(
                        name=skill,
                        level=SkillLevel.WORKING,
                        evidence_keys=supporting,
                    )
                )
        if not skills:
            skills.append(
                ProposedSkill(
                    name="General Experience",
                    level=SkillLevel.UNKNOWN,
                    evidence_keys=(evidence[0].key,),
                )
            )

        years_match = re.search(r"(\d+(?:\.\d+)?)\s*年", resume_text)
        years = float(years_match.group(1)) if years_match else None
        return ProfileExtractorResult(
            output=ProfileExtractionOutput(
                headline=lines[0][:500],
                years_of_experience=years,
                evidence=evidence,
                skills=tuple(skills),
                warnings=(
                    "Fixture extractor is active; use the OpenAI provider for live extraction.",
                ),
            ),
            model=self.model_name,
            input_tokens=None,
            output_tokens=None,
        )


class OpenAIProfileExtractor(AbstractProfileExtractor):
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

    def extract(self, resume_text: str) -> ProfileExtractorResult:
        if not self._api_key or not self._model:
            raise ProfileExtractorUnavailableError(
                "OpenAI Profile extractor requires OPENAI_API_KEY and PROFILE_EXTRACTOR_MODEL."
            )

        schema = _ProfileOutput.model_json_schema(by_alias=True)
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
                        "content": [{"type": "input_text", "text": resume_text}],
                    },
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "profile_extraction_proposal",
                        "description": "Evidence-grounded career Profile proposal",
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
                    {"role": "user", "content": resume_text},
                ],
                "stream": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "profile_extraction_proposal",
                        "description": "Evidence-grounded career Profile proposal",
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
            raise ProfileExtractorUnavailableError(
                "OpenAI Profile extractor API style must be responses or chat_completions."
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
            parsed = _ProfileOutput.model_validate_json(output_text(payload))
        except ProfileExtractorFailedError:
            raise
        except httpx.HTTPStatusError as error:
            trace_id = _response_trace_id(error.response)
            trace_suffix = f", traceId={trace_id}" if trace_id else ""
            raise ProfileExtractorFailedError(
                "OpenAI Profile extractor failed: "
                f"HTTPStatusError(status={error.response.status_code}{trace_suffix})"
            ) from error
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError) as error:
            raise ProfileExtractorFailedError(
                f"OpenAI Profile extractor failed: {type(error).__name__}"
            ) from error

        usage = payload.get("usage") if isinstance(payload, dict) else None
        input_tokens = _optional_int(usage, input_tokens_key)
        output_tokens = _optional_int(usage, output_tokens_key)
        return ProfileExtractorResult(
            output=ProfileExtractionOutput(
                headline=parsed.headline,
                years_of_experience=parsed.years_of_experience,
                evidence=tuple(
                    ProposedEvidence(
                        key=item.key,
                        type=item.type,
                        summary=item.summary,
                        source=item.source,
                        evidence_span=item.evidence_span,
                    )
                    for item in parsed.evidence
                ),
                skills=tuple(
                    ProposedSkill(
                        name=item.name,
                        level=item.level,
                        evidence_keys=tuple(item.evidence_keys),
                    )
                    for item in parsed.skills
                ),
                warnings=tuple(parsed.warnings),
            ),
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def _fixture_evidence_type(line: str) -> EvidenceType:
    if "教育" in line or "大学" in line or "学历" in line:
        return EvidenceType.EDUCATION
    if "获奖" in line or "成绩" in line or "提升" in line:
        return EvidenceType.ACHIEVEMENT
    if "项目" in line:
        return EvidenceType.PROJECT
    if "工作" in line or "负责" in line:
        return EvidenceType.WORK
    if "自述" in line:
        return EvidenceType.SELF_REPORT
    return EvidenceType.PROJECT


def _response_output_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ProfileExtractorFailedError("OpenAI response must be a JSON object")
    for item in _iter_dicts(payload.get("output")):
        if item.get("type") != "message":
            continue
        for content in _iter_dicts(item.get("content")):
            if content.get("type") == "refusal":
                raise ProfileExtractorFailedError("OpenAI refused Profile extraction")
            if content.get("type") == "output_text" and isinstance(
                content.get("text"), str
            ):
                return content["text"]
    raise ProfileExtractorFailedError("OpenAI response contained no output_text")


def _chat_completion_output_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ProfileExtractorFailedError(
            "OpenAI Chat Completions response must be a JSON object"
        )
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProfileExtractorFailedError(
            "OpenAI Chat Completions response contained no choices"
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ProfileExtractorFailedError(
            "OpenAI Chat Completions choice must be a JSON object"
        )
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ProfileExtractorFailedError(
            "OpenAI Chat Completions response contained no message"
        )
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal:
        raise ProfileExtractorFailedError("OpenAI refused Profile extraction")
    content = message.get("content")
    if isinstance(content, str) and content:
        return content
    for item in _iter_dicts(content):
        if item.get("type") == "refusal":
            raise ProfileExtractorFailedError("OpenAI refused Profile extraction")
        if item.get("type") in {"text", "output_text"} and isinstance(
            item.get("text"), str
        ):
            return item["text"]
    raise ProfileExtractorFailedError(
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


_SYSTEM_PROMPT = """You extract a reviewable career Profile proposal from resume text.

Rules:
- Extract only facts explicitly supported by the resume.
- Never invent companies, projects, achievements, years, metrics, or skills.
- Every Evidence item must include evidenceSpan copied verbatim as one contiguous substring from the resume.
- Every Skill must reference one or more Evidence keys from the same output.
- Omit unsupported skills instead of guessing.
- Do not infer target roles, salary, city, remote preference, or other SearchIntent fields.
- Use source='resume'.
- Keep evidence summaries concise and factual.
"""
