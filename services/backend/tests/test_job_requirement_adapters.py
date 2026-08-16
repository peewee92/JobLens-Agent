"""Provider-adapter tests for Job Requirement Extraction."""
from __future__ import annotations

import json

import httpx
import pytest

from app.application.job_requirements import (
    RequirementExtractorFailedError,
    RequirementExtractorUnavailableError,
)
from app.llm import OpenAIJobRequirementExtractor


def test_openai_requirement_adapter_uses_strict_schema_and_no_storage() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        output = {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "熟练掌握 Python 和 FastAPI",
                    "normalizedCapability": "Python",
                    "importance": "must_have",
                    "evidenceSpan": "熟练掌握 Python 和 FastAPI",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps(output)}
                        ],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 40},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            client=client,
        ).extract("岗位要求：熟练掌握 Python 和 FastAPI，并具备后端系统设计经验。")

    assert captured["model"] == "test-model"
    assert captured["store"] is False
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True
    assert captured["text"]["format"]["schema"]["additionalProperties"] is False
    assert result.output.requirements[0].normalized_capability == "Python"
    assert result.input_tokens == 100
    assert result.output_tokens == 40


def test_openai_requirement_adapter_prompt_preserves_requirement_importance_scope() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        output = {
            "requirements": [
                {
                    "type": "education",
                    "originalText": "本科及以上学历",
                    "normalizedCapability": None,
                    "importance": "must_have",
                    "evidenceSpan": "本科及以上学历",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            client=client,
        ).extract("任职要求：本科及以上学历，计算机相关专业优先。")

    prompt = captured["messages"][0]["content"]
    assert "requirements/qualifications section" in prompt
    assert "default to must_have" in prompt
    assert "applies only to the clause it modifies" in prompt
    assert "split them into separate requirements" in prompt
    assert "at least N" in prompt
    assert "must not make every child independently must_have" in prompt
    assert "waiver or exception" in prompt
    assert "可放宽" in prompt
    assert "examples such as" in prompt
    assert "must not become independent must_have requirements" in prompt


def test_openai_requirement_adapter_schema_requires_normalized_capability_for_skills() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        output = {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "熟练掌握 Python",
                    "normalizedCapability": "Python",
                    "importance": "must_have",
                    "evidenceSpan": "熟练掌握 Python",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            client=client,
        ).extract("岗位要求：熟练掌握 Python。")

    schema = captured["response_format"]["json_schema"]["schema"]
    skill_schema = schema["$defs"]["_SkillRequirementOutput"]
    other_schema = schema["$defs"]["_OtherRequirementOutput"]
    assert skill_schema["properties"]["type"]["const"] == "skill"
    assert skill_schema["properties"]["normalizedCapability"]["type"] == "string"
    assert skill_schema["properties"]["normalizedCapability"]["minLength"] == 1
    assert {item.get("type") for item in other_schema["properties"]["normalizedCapability"]["anyOf"]} == {"string", "null"}


def test_openai_requirement_adapter_rejects_skill_without_normalized_capability() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        output = {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "具备业务理解能力",
                    "normalizedCapability": None,
                    "importance": "preferred",
                    "evidenceSpan": "具备业务理解能力",
                    "confidence": 0.9,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            client=client,
        )
        with pytest.raises(RequirementExtractorFailedError, match="ValidationError"):
            extractor.extract("岗位要求：具备业务理解能力。")


def test_openai_requirement_adapter_supports_chat_completions_strict_schema() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured.update(json.loads(request.content))
        output = {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "熟练掌握 Python 和 FastAPI",
                    "normalizedCapability": "Python",
                    "importance": "must_have",
                    "evidenceSpan": "熟练掌握 Python 和 FastAPI",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            enable_thinking=False,
            max_completion_tokens=8192,
            client=client,
        ).extract("岗位要求：熟练掌握 Python 和 FastAPI，并具备后端系统设计经验。")

    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["model"] == "test-model"
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][1]["role"] == "user"
    assert captured["stream"] is False
    assert captured["enable_thinking"] is False
    assert captured["max_completion_tokens"] == 8192
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert (
        captured["response_format"]["json_schema"]["schema"]["additionalProperties"]
        is False
    )
    assert "store" not in captured
    assert result.output.requirements[0].normalized_capability == "Python"
    assert result.input_tokens == 100
    assert result.output_tokens == 40


@pytest.mark.parametrize("status_code", [429, 503, 504])
def test_openai_requirement_adapter_classifies_transient_provider_outage_as_unavailable(
    status_code: int,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            headers={"x-trace-id": "trace_gateway_123"},
            json={"error": {"message": "temporary upstream outage"}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            api_style="chat_completions",
            client=client,
        )
        with pytest.raises(
            RequirementExtractorUnavailableError,
            match=rf"HTTPStatusError\(status={status_code}, traceId=trace_gateway_123\)",
        ):
            extractor.extract(
                "岗位要求熟练掌握 Python 和 FastAPI，并具备后端开发经验。"
            )


def test_openai_requirement_adapter_keeps_non_transient_http_error_as_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "internal error"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            api_style="chat_completions",
            client=client,
        )
        with pytest.raises(
            RequirementExtractorFailedError,
            match=r"HTTPStatusError\(status=500\)",
        ):
            extractor.extract(
                "岗位要求熟练掌握 Python 和 FastAPI，并具备后端开发经验。"
            )


def test_openai_requirement_adapter_requires_configuration() -> None:
    extractor = OpenAIJobRequirementExtractor(api_key=None, model="")

    with pytest.raises(RequirementExtractorUnavailableError):
        extractor.extract("岗位要求熟练掌握 Python 和 FastAPI，并具备后端开发经验。")


def test_openai_requirement_adapter_maps_refusal() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "refusal", "refusal": "cannot comply"}
                        ],
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            client=client,
        )
        with pytest.raises(RequirementExtractorFailedError, match="refused"):
            extractor.extract(
                "岗位要求熟练掌握 Python 和 FastAPI，并具备后端开发经验。"
            )
