"""Provider-adapter tests for Profile Extraction."""
from __future__ import annotations

import json

import httpx
import pytest

from app.application.profile_extraction import (
    ProfileExtractorFailedError,
    ProfileExtractorUnavailableError,
)
from app.llm import OpenAIProfileExtractor


def test_openai_adapter_requests_strict_schema_without_storage() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        output = {
            "headline": "8 年前端工程师",
            "yearsOfExperience": 8,
            "evidence": [
                {
                    "key": "work-1",
                    "type": "work",
                    "summary": "负责 React 平台开发",
                    "source": "resume",
                    "evidenceSpan": "负责 React 平台开发",
                }
            ],
            "skills": [
                {
                    "name": "React",
                    "level": "strong",
                    "evidenceKeys": ["work-1"],
                }
            ],
            "warnings": [],
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
                "usage": {"input_tokens": 120, "output_tokens": 70},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIProfileExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            client=client,
        ).extract(
            "8 年前端工程师。工作经历：负责 React 平台开发，并完成复杂业务模块交付。"
        )

    assert captured["model"] == "test-model"
    assert captured["store"] is False
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True
    assert captured["text"]["format"]["schema"]["additionalProperties"] is False
    assert result.output.skills[0].name == "React"
    assert result.input_tokens == 120
    assert result.output_tokens == 70


def test_openai_adapter_supports_chat_completions_gateway_controls() -> None:
    captured: dict = {}
    captured_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_url
        captured_url = str(request.url)
        captured.update(json.loads(request.content))
        output = {
            "headline": "8 年前端工程师",
            "yearsOfExperience": 8,
            "evidence": [
                {
                    "key": "work-1",
                    "type": "work",
                    "summary": "负责 React 平台开发",
                    "source": "resume",
                    "evidenceSpan": "负责 React 平台开发",
                }
            ],
            "skills": [
                {
                    "name": "React",
                    "level": "strong",
                    "evidenceKeys": ["work-1"],
                }
            ],
            "warnings": [],
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(output)}}],
                "usage": {"prompt_tokens": 121, "completion_tokens": 71},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIProfileExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            enable_thinking=False,
            max_completion_tokens=4096,
            client=client,
        ).extract(
            "8 年前端工程师。工作经历：负责 React 平台开发，并完成复杂业务模块交付。"
        )

    assert captured_url == "https://example.test/v1/chat/completions"
    assert captured["stream"] is False
    assert captured["enable_thinking"] is False
    assert captured["max_completion_tokens"] == 4096
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert result.output.skills[0].name == "React"
    assert result.input_tokens == 121
    assert result.output_tokens == 71


def test_openai_chat_completions_error_preserves_gateway_trace_id() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, json={"traceId": "trace-profile-123"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIProfileExtractor(
            api_key="test-key",
            model="test-model",
            api_style="chat_completions",
            client=client,
        )
        with pytest.raises(ProfileExtractorFailedError, match="trace-profile-123"):
            extractor.extract(
                "8 年前端经验。负责 React 开发，所有内容均来自简历事实。"
            )


def test_openai_adapter_requires_credentials_and_model() -> None:
    extractor = OpenAIProfileExtractor(api_key=None, model="")

    with pytest.raises(ProfileExtractorUnavailableError):
        extractor.extract("This resume text is long enough but configuration is missing.")


def test_openai_adapter_maps_refusal_to_provider_failure() -> None:
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
        extractor = OpenAIProfileExtractor(
            api_key="test-key",
            model="test-model",
            client=client,
        )
        with pytest.raises(ProfileExtractorFailedError, match="refused"):
            extractor.extract(
                "8 年前端经验。负责 React 开发，所有内容均来自简历事实。"
            )
