"""Job Requirement Extractor adapters for disabled, fixture and OpenAI providers."""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
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
    importance: RequirementImportance
    evidence_span: str = Field(alias="evidenceSpan", min_length=1, max_length=4000)
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


class _RequirementsOutput(_StrictModel):
    requirements: list[_RequirementOutput] = Field(min_length=1, max_length=50)


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

    def extract(self, description: str) -> JobRequirementExtractorResult:
        if not self._api_key or not self._model:
            raise RequirementExtractorUnavailableError(
                "OpenAI Requirement extractor requires OPENAI_API_KEY and REQUIREMENT_EXTRACTOR_MODEL."
            )
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
                        "content": [{"type": "input_text", "text": description}],
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
                    {"role": "user", "content": description},
                ],
                "stream": False,
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
            parsed = _RequirementsOutput.model_validate_json(output_text(payload))
        except RequirementExtractorFailedError:
            raise
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            trace_id = _response_trace_id(error.response)
            trace_suffix = f", traceId={trace_id}" if trace_id else ""
            error_type = (
                RequirementExtractorUnavailableError
                if status_code in {429, 503, 504}
                else RequirementExtractorFailedError
            )
            raise error_type(
                "OpenAI Requirement extractor failed: "
                f"HTTPStatusError(status={status_code}{trace_suffix})"
            ) from error
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError) as error:
            raise RequirementExtractorFailedError(
                f"OpenAI Requirement extractor failed: {type(error).__name__}"
            ) from error

        usage = payload.get("usage") if isinstance(payload, dict) else None
        return JobRequirementExtractorResult(
            output=JobRequirementExtractionOutput(
                requirements=tuple(
                    ProposedJobRequirement(
                        type=item.type,
                        original_text=item.original_text,
                        normalized_capability=item.normalized_capability,
                        importance=item.importance,
                        evidence_span=item.evidence_span,
                        confidence=item.confidence,
                    )
                    for item in parsed.requirements
                )
            ),
            model=self._model,
            input_tokens=_optional_int(usage, input_tokens_key),
            output_tokens=_optional_int(usage, output_tokens_key),
        )


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
        raise RequirementExtractorFailedError("OpenAI response must be a JSON object")
    for item in _iter_dicts(payload.get("output")):
        if item.get("type") != "message":
            continue
        for content in _iter_dicts(item.get("content")):
            if content.get("type") == "refusal":
                raise RequirementExtractorFailedError("OpenAI refused Requirement extraction")
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise RequirementExtractorFailedError("OpenAI response contained no output_text")


def _chat_completion_output_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise RequirementExtractorFailedError(
            "OpenAI Chat Completions response must be a JSON object"
        )
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RequirementExtractorFailedError(
            "OpenAI Chat Completions response contained no choices"
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise RequirementExtractorFailedError(
            "OpenAI Chat Completions choice must be a JSON object"
        )
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RequirementExtractorFailedError(
            "OpenAI Chat Completions response contained no message"
        )
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal:
        raise RequirementExtractorFailedError("OpenAI refused Requirement extraction")
    content = message.get("content")
    if isinstance(content, str) and content:
        return content
    for item in _iter_dicts(content):
        if item.get("type") == "refusal":
            raise RequirementExtractorFailedError("OpenAI refused Requirement extraction")
        if item.get("type") in {"text", "output_text"} and isinstance(
            item.get("text"), str
        ):
            return item["text"]
    raise RequirementExtractorFailedError(
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


_SYSTEM_PROMPT = """Extract structured JobRequirements from one Job description.

Rules:
- Extract only requirements explicitly present in the Job description.
- Never infer requirements from the job title, company, industry stereotypes, or general knowledge.
- Each originalText and evidenceSpan must be copied verbatim as one contiguous substring from the input.
- Classify type as skill, experience, education, responsibility, domain, or constraint.
- Classify importance by the requirement's actual scope. In an explicit requirements/qualifications section, default to must_have unless that exact requirement is softened by optional/preferred/bonus wording.
- A softening modifier such as 优先/加分/preferred/optional applies only to the clause it modifies; do not downgrade adjacent hard constraints in the same sentence. If one sentence mixes hard and soft clauses, split them into separate requirements when the input provides separable verbatim spans.
- For alternative or cardinality groups such as "at least N of the following", "one of", "any one", or "任意一种", preserve the group constraint as must_have but must not make every child independently must_have unless the Job description explicitly requires every child. Child capabilities may be preferred when they are alternatives under the mandatory group constraint.
- Use bonus only for explicitly optional, plus, preferred, or bonus requirements. Use preferred only for explicitly desirable-but-not-mandatory requirements or alternative child capabilities governed by a separate mandatory group constraint.
- Normalize capability aliases when supported by the text, for example React.js/ReactJS → React.
- Skill requirements must include normalizedCapability.
- Omit unsupported requirements instead of guessing.
- Return no prose outside the strict schema.
"""
